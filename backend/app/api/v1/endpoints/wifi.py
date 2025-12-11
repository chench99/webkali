from fastapi import APIRouter, Body, Depends
from sqlmodel import Session, select, delete
from app.core.database import get_session
from app.models.wifi import WiFiNetwork, TargetedClient, DeepScanClient
from pydantic import BaseModel
from typing import List, Dict, Optional
import time
import asyncio

router = APIRouter()

# --- C2 状态机 (内存) ---
c2_state = {
    "interfaces": [],
    "current_task": None,  # 当前任务: 'scan', 'monitor_target', 'deep_scan'
    "task_params": {},  # 任务参数: { 'bssid': ..., 'channel': ... }
    "last_heartbeat": 0,
    "monitoring_data": {}  # 临时缓存实时监听数据，用于前端轮询
}


# ==========================================
# 1. 前端指令接口 (下发任务)
# ==========================================

class MonitorReq(BaseModel):
    bssid: str
    channel: int


@router.post("/monitor/start")
async def start_target_monitor(req: MonitorReq):
    """前端点击“监听” -> 设置 C2 任务为 monitor_target"""
    print(f"[*] C2 指令: 锁定监听 {req.bssid} (CH {req.channel})")
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = {
        'bssid': req.bssid,
        'channel': req.channel,
        'duration': 0  # 0表示一直运行直到停止
    }
    return {"status": "queued", "msg": "监听指令已进入队列，等待 Agent 领取"}


@router.post("/monitor/deep")
async def start_deep_scan(db: Session = Depends(get_session)):
    """前端点击“深度扫描” -> 清空表 -> 设置 C2 任务为 deep_scan"""
    print("[*] C2 指令: 开启全网深度扫描")

    # 1. 清空旧数据 (符合需求)
    db.exec(delete(DeepScanClient))
    db.commit()

    # 2. 下发任务
    c2_state['current_task'] = 'deep_scan'
    c2_state['task_params'] = {}

    return {"status": "queued", "msg": "深度扫描已启动，历史数据已清空"}


@router.post("/monitor/stop")
async def stop_all_tasks():
    """停止所有任务"""
    c2_state['current_task'] = 'idle'
    c2_state['task_params'] = {}
    return {"status": "stopped"}


# ==========================================
# 2. Agent 交互接口 (Kali 调用)
# ==========================================

@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Agent 心跳：领取任务"""
    c2_state['last_heartbeat'] = time.time()

    # 如果有任务，下发给 Agent
    if c2_state['current_task']:
        return {
            "status": "ok",
            "task": c2_state['current_task'],
            "params": c2_state['task_params']
        }
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    type: str  # 'scan_result', 'monitor_update', 'deep_update'
    data: List[Dict]


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    """接收 Agent 回传的数据并入库"""
    # print(f"[*] 收到 Agent 回调: {payload.type} ({len(payload.data)} 条)")

    # A. 处理定向监听数据
    if payload.type == 'monitor_update':
        bssid = c2_state['task_params'].get('bssid')
        for item in payload.data:
            # 这里的 item 结构由 Agent 定义
            client_mac = item.get('mac')
            if not client_mac: continue

            # 更新或插入
            existing = db.exec(select(TargetedClient).where(
                TargetedClient.client_mac == client_mac,
                TargetedClient.network_bssid == bssid
            )).first()

            if not existing:
                new_client = TargetedClient(
                    network_bssid=bssid,
                    client_mac=client_mac,
                    packet_count=item.get('packets', 0),
                    signal=item.get('power', 0)
                )
                db.add(new_client)
            else:
                existing.packet_count = item.get('packets', 0)
                existing.signal = item.get('power', 0)
                existing.last_seen = datetime.utcnow()
        db.commit()

    # B. 处理深度扫描数据
    elif payload.type == 'deep_update':
        for item in payload.data:
            client_mac = item.get('mac')
            if not client_mac: continue

            existing = db.exec(select(DeepScanClient).where(DeepScanClient.client_mac == client_mac)).first()

            if not existing:
                new_c = DeepScanClient(
                    client_mac=client_mac,
                    connected_bssid=item.get('bssid'),
                    probed_essids=item.get('probed'),
                    signal=item.get('power', 0),
                    capture_channel=item.get('channel', 0),
                    vendor="Unknown"  # 可后续加 OUI 查询
                )
                db.add(new_c)
            else:
                # 更新最有价值的 Probed 字段
                new_probed = item.get('probed')
                if new_probed and len(new_probed) > len(existing.probed_essids or ""):
                    existing.probed_essids = new_probed
                existing.last_seen = datetime.utcnow()
        db.commit()

    return {"status": "received"}


# ==========================================
# 3. 前端数据获取接口
# ==========================================

@router.get("/monitor/clients/{bssid}")
async def get_targeted_clients(bssid: str, db: Session = Depends(get_session)):
    """获取指定 WiFi 的在线终端"""
    clients = db.exec(select(TargetedClient).where(TargetedClient.network_bssid == bssid)).all()
    return clients


@router.get("/monitor/deep_results")
async def get_deep_scan_results(db: Session = Depends(get_session)):
    """获取深度扫描结果"""
    clients = db.exec(select(DeepScanClient).order_by(DeepScanClient.last_seen.desc())).all()
    return clients