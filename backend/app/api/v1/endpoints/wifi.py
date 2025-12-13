from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select, delete
from app.core.database import get_session
from app.models.wifi import WiFiNetwork, TargetedClient, DeepScanClient
from app.core.ssh_manager import ssh_client
from pydantic import BaseModel
from typing import List, Dict, Optional
import time
import asyncio
from datetime import datetime
from pathlib import Path

router = APIRouter()

# --- C2 状态机 (内存) ---
c2_state = {
    "interfaces": [],
    "current_task": "idle",
    "task_params": {},
    "last_heartbeat": 0,
    "networks": []
}

scan_complete_event = asyncio.Event()


# ... (省略 deploy_agent_via_ssh 和 get_interfaces 代码，保持不变) ...

# ==========================================
# 3. 任务控制接口 (监听/扫描/停止)
# ==========================================

class MonitorReq(BaseModel):
    bssid: str
    channel: int


@router.post("/monitor/start")
async def start_target_monitor(req: MonitorReq, db: Session = Depends(get_session)):
    """[C2] 启动定向监听"""
    print(f"[*] C2 指令: 锁定监听 {req.bssid} (CH {req.channel})")

    # 1. 清空该 BSSID 的历史监听记录，保证数据新鲜 (可选)
    # db.exec(delete(TargetedClient).where(TargetedClient.network_bssid == req.bssid))
    # db.commit()

    # 2. 设置 C2 任务，等待 Agent 拉取
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = {
        'bssid': req.bssid,
        'channel': req.channel
    }
    return {"status": "queued", "msg": "监听指令已下发"}


@router.post("/monitor/deep")
async def start_deep_scan(db: Session = Depends(get_session)):
    """[C2] 启动深度全网扫描"""
    db.exec(delete(DeepScanClient))
    db.commit()
    c2_state['current_task'] = 'deep_scan'
    c2_state['task_params'] = {}
    return {"status": "queued", "msg": "深度扫描已启动"}


@router.post("/monitor/stop")
async def stop_all_tasks():
    """[C2] 停止所有任务"""
    print("[*] C2 指令: 停止任务")
    c2_state['current_task'] = 'idle'
    c2_state['task_params'] = {}
    return {"status": "stopped"}


class ScanReq(BaseModel):
    interface: Optional[str]


@router.post("/scan/start")
async def trigger_scan(req: ScanReq = Body(None)):
    """[C2] 触发普通扫描"""
    print("[*] C2 指令: 普通扫描请求")
    scan_complete_event.clear()

    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        # 阻塞等待 Agent 回调 (最长 20s)
        await asyncio.wait_for(scan_complete_event.wait(), timeout=20.0)
        return {"status": "success", "networks": c2_state['networks']}
    except asyncio.TimeoutError:
        c2_state['current_task'] = 'idle'
        return {"status": "timeout", "message": "Agent 响应超时"}


@router.get("/networks")
async def get_networks_cache():
    return c2_state['networks']


# ==========================================
# 4. Agent 交互接口 (核心)
# ==========================================

class AgentInfo(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(info: AgentInfo):
    c2_state['interfaces'] = info.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "registered"}


@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Agent 轮询任务"""
    c2_state['last_heartbeat'] = time.time()
    if c2_state['current_task'] != 'idle':
        return {
            "status": "ok",
            "task": c2_state['current_task'],
            "params": c2_state['task_params']
        }
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    type: str  # 'scan_result', 'monitor_update', 'deep_update'
    networks: Optional[List[Dict]] = None
    data: Optional[List[Dict]] = None  # 监听到的客户端列表


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    """处理 Agent 回传数据"""

    # 1. 普通扫描结果
    if payload.type == 'scan_result' and payload.networks is not None:
        print(f"[*] 收到扫描结果: {len(payload.networks)} 个网络")
        c2_state['networks'] = payload.networks
        c2_state['current_task'] = 'idle'
        scan_complete_event.set()
        return {"status": "received"}

    # 2. 定向监听数据回传 (入库逻辑)
    if payload.type == 'monitor_update' and payload.data:
        target_bssid = c2_state['task_params'].get('bssid')

        for item in payload.data:
            client_mac = item.get('mac')
            if not client_mac: continue

            # 查询是否已存在记录
            existing = db.exec(select(TargetedClient).where(
                TargetedClient.client_mac == client_mac,
                TargetedClient.network_bssid == target_bssid
            )).first()

            # 解析数据
            try:
                pkt_cnt = int(item.get('packets', 0))
            except:
                pkt_cnt = 0
            try:
                sig = int(item.get('power', 0))
            except:
                sig = 0

            if not existing:
                # 新增记录
                db.add(TargetedClient(
                    network_bssid=target_bssid,
                    client_mac=client_mac,
                    packet_count=pkt_cnt,
                    signal=sig,
                    last_seen=datetime.utcnow()
                ))
            else:
                # 更新活跃状态
                existing.packet_count = pkt_cnt
                existing.signal = sig
                existing.last_seen = datetime.utcnow()

        db.commit()
        return {"status": "updated"}

    return {"status": "ok"}


# ==========================================
# 5. 前端查询接口
# ==========================================
@router.get("/monitor/clients/{bssid}")
async def get_targeted_clients(bssid: str, db: Session = Depends(get_session)):
    """前端轮询此接口，获取入库的客户端数据"""
    clients = db.exec(select(TargetedClient).where(TargetedClient.network_bssid == bssid)).all()
    return clients