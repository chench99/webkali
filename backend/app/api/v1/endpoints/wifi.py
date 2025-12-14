from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select, delete
from app.core.database import get_session
# 确保引入了 TargetedClient 模型
from app.models.wifi import WiFiNetwork, TargetedClient
from app.core.ssh_manager import ssh_client
from pydantic import BaseModel
from typing import List, Dict, Optional
import time
import asyncio
from datetime import datetime
from pathlib import Path

router = APIRouter()

# --- C2 状态机 (内存缓存) ---
c2_state = {
    "interfaces": [],  # Agent 网卡列表
    "current_task": "idle",  # 当前任务: idle, scan, monitor_target
    "task_params": {},  # 任务参数
    "last_heartbeat": 0,  # 上次心跳
    "networks": []  # 扫描结果缓存
}

# 异步事件：用于在 scan 接口等待 Agent 完成
scan_complete_event = asyncio.Event()


# ==========================================
# 1. 任务控制接口 (前端调用)
# ==========================================

class ScanReq(BaseModel):
    interface: str = "wlan0"


@router.post("/scan/start")
async def trigger_scan(req: ScanReq):
    """
    [前端] 触发扫描任务
    此接口会阻塞，直到 Agent 回传结果或超时
    """
    # 1. 设置任务状态
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}
    c2_state['networks'] = []  # 清空旧数据

    print(f"[*] 下发扫描任务 -> Interface: {req.interface}")

    try:
        # 2. 阻塞等待 Agent 回调 (超时 20 秒)
        await asyncio.wait_for(scan_complete_event.wait(), timeout=20.0)
        return {"status": "success", "networks": c2_state['networks']}
    except asyncio.TimeoutError:
        # 超时处理
        c2_state['current_task'] = 'idle'
        return {"status": "timeout", "message": "Agent 响应超时，请检查 Agent 是否在线"}


class MonitorReq(BaseModel):
    bssid: str
    channel: int
    interface: str = "wlan0"


@router.post("/monitor/start")
async def start_monitor(req: MonitorReq, db: Session = Depends(get_session)):
    """
    [前端] 启动定向监听任务
    """
    # 1. 清理该目标旧的监听数据 (可选，看需求，这里选择保留历史数据，只清内存状态)

    # 2. 设置任务
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = {
        'bssid': req.bssid,
        'channel': req.channel,
        'interface': req.interface
    }

    print(f"[*] 下发监听任务 -> Target: {req.bssid} CH: {req.channel}")
    return {"status": "queued", "msg": "监听指令已下发"}


@router.post("/monitor/stop")
async def stop_monitor():
    """
    [前端] 停止所有任务
    """
    c2_state['current_task'] = 'idle'
    c2_state['task_params'] = {}
    print("[*] 停止任务指令已下发")
    return {"status": "stopped"}


# ==========================================
# 2. 数据查询接口 (前端轮询)
# ==========================================

@router.get("/interfaces")
async def get_interfaces():
    """获取网卡列表，附带在线状态判断"""
    is_online = (time.time() - c2_state['last_heartbeat']) < 15
    if not c2_state['interfaces'] or not is_online:
        # 返回一个虚拟的等待状态
        return {"interfaces": [{"name": "waiting", "display": "等待 Agent 连接...", "mode": "-"}]}
    return {"interfaces": c2_state['interfaces']}


@router.get("/networks")
async def get_networks_cache():
    """获取缓存的扫描结果"""
    return c2_state['networks']


@router.get("/monitor/clients/{bssid}")
async def get_monitored_clients(bssid: str, db: Session = Depends(get_session)):
    """
    [前端轮询] 获取数据库中存储的监听结果
    """
    # 查询该 BSSID 下的所有客户端，按信号强度或最后出现时间排序
    statement = select(TargetedClient).where(
        TargetedClient.network_bssid == bssid
    ).order_by(TargetedClient.last_seen.desc())

    results = db.exec(statement).all()
    return results


# ==========================================
# 3. Agent 交互接口 (Heartbeat & Callback)
# ==========================================

class AgentRegister(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(data: AgentRegister):
    """Agent 上报网卡"""
    c2_state['interfaces'] = data.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "ok"}


@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Agent 领取任务 (Long Polling 逻辑可在此扩展)"""
    c2_state['last_heartbeat'] = time.time()

    # 只要不是 idle，就持续下发当前任务配置
    if c2_state['current_task'] != 'idle':
        return {
            "status": "ok",
            "task": c2_state['current_task'],
            "params": c2_state['task_params']
        }
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    type: str  # 'scan_result' | 'monitor_update'
    networks: Optional[List[Dict]] = None
    data: Optional[List[Dict]] = None  # 通用数据负载


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    """接收 Agent 回传的数据"""

    # === 处理扫描结果 ===
    if payload.type == 'scan_result' and payload.networks is not None:
        print(f"[*] 收到扫描结果: {len(payload.networks)} 个网络")
        c2_state['networks'] = payload.networks
        c2_state['current_task'] = 'idle'  # 扫描是一次性的，完成后重置为 idle
        scan_complete_event.set()  # 解除 await 阻塞
        return {"status": "received"}

    # === 处理监听数据 (入库) ===
    if payload.type == 'monitor_update' and payload.data:
        # print(f"[*] 收到监听数据: {len(payload.data)} 个客户端")

        target_bssid = c2_state['task_params'].get('bssid')
        if not target_bssid:
            return {"status": "ignored", "msg": "No target monitored"}

        for client in payload.data:
            mac = client.get('mac')
            if not mac: continue

            # Upsert 逻辑: 检查是否存在
            existing = db.exec(select(TargetedClient).where(
                TargetedClient.client_mac == mac,
                TargetedClient.network_bssid == target_bssid
            )).first()

            if existing:
                # 更新
                existing.signal = client.get('signal', -100)
                existing.packet_count = client.get('packets', 0)
                existing.last_seen = datetime.utcnow()
                db.add(existing)
            else:
                # 插入
                new_client = TargetedClient(
                    network_bssid=target_bssid,
                    client_mac=mac,
                    signal=client.get('signal', -100),
                    packet_count=client.get('packets', 0),
                    last_seen=datetime.utcnow()
                )
                db.add(new_client)

        db.commit()
        return {"status": "updated"}

    return {"status": "ok"}