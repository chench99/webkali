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
    "interfaces": [],  # Agent 上报的网卡列表
    "current_task": "idle",  # 当前任务
    "task_params": {},  # 任务参数
    "last_heartbeat": 0,  # 上次心跳时间
    "networks": []  # 扫描结果缓存
}

scan_complete_event = asyncio.Event()


# ==========================================
# 1. 部署与连接管理
# ==========================================

@router.post("/agent/deploy")
async def deploy_agent_via_ssh():
    """[C2] 远程部署接口"""
    print("[*] 收到 Agent 部署指令...")

    if not ssh_client.client:
        ssh_client.connect()
        if not ssh_client.client:
            return {"status": "error", "message": "SSH 连接失败"}

    # 智能定位 Payload 路径
    current_file = Path(__file__).resolve()
    possible_paths = [
        current_file.parents[5] / "kali_payloads" / "wifi_scanner.py",
        current_file.parents[4] / "kali_payloads" / "wifi_scanner.py",
        Path.cwd() / "kali_payloads" / "wifi_scanner.py",
        Path.cwd().parent / "kali_payloads" / "wifi_scanner.py"
    ]

    payload_path = None
    for p in possible_paths:
        if p.exists():
            payload_path = p
            break

    if not payload_path:
        return {"status": "error", "message": "服务端找不到 wifi_scanner.py"}

    try:
        # 上传脚本
        remote_path = ssh_client.upload_payload(str(payload_path), "wifi_scanner.py")
        if not remote_path:
            return {"status": "error", "message": "SFTP 上传失败"}

        # 注入 C2 IP
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "127.0.0.1"

        ssh_client.exec_command(f"sed -i 's/FIXED_C2_IP = \"\"/FIXED_C2_IP = \"{local_ip}\"/g' {remote_path}")

        # 启动进程
        ssh_client.exec_command("pkill -f wifi_scanner.py")
        cmd = f"nohup python3 {remote_path} > /tmp/agent.log 2>&1 &"
        ssh_client.exec_command(cmd)

        return {"status": "success", "message": "Agent 已启动，等待心跳..."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ⚠️ 之前报 404 就是因为这个接口可能丢失了
@router.get("/interfaces")
async def get_interfaces():
    """[前端调用] 获取 Agent 网卡列表"""
    # 简单的在线状态判断 (15秒无心跳视为离线)
    is_online = (time.time() - c2_state['last_heartbeat']) < 15

    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "Agent 离线/等待中...", "is_wireless": False}]}

    return {"interfaces": c2_state['interfaces']}


# ==========================================
# 2. 任务控制接口
# ==========================================

class MonitorReq(BaseModel):
    bssid: str
    channel: int


@router.post("/monitor/start")
async def start_target_monitor(req: MonitorReq):
    """启动定向监听"""
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = {'bssid': req.bssid, 'channel': req.channel}
    return {"status": "queued", "msg": "监听指令已下发"}


@router.post("/monitor/deep")
async def start_deep_scan(db: Session = Depends(get_session)):
    """启动深度扫描"""
    db.exec(delete(DeepScanClient))
    db.commit()
    c2_state['current_task'] = 'deep_scan'
    c2_state['task_params'] = {}
    return {"status": "queued", "msg": "深度扫描已启动"}


@router.post("/monitor/stop")
async def stop_all_tasks():
    """停止任务"""
    c2_state['current_task'] = 'idle'
    c2_state['task_params'] = {}
    return {"status": "stopped"}


class ScanReq(BaseModel):
    interface: Optional[str]


@router.post("/scan/start")
async def trigger_scan(req: ScanReq = Body(None)):
    """触发普通扫描"""
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        # 等待 Agent 回调结果
        await asyncio.wait_for(scan_complete_event.wait(), timeout=20.0)
        return {"status": "success", "networks": c2_state['networks']}
    except asyncio.TimeoutError:
        c2_state['current_task'] = 'idle'
        return {"status": "timeout", "message": "Agent 响应超时"}


@router.get("/networks")
async def get_networks_cache():
    return c2_state['networks']


# ==========================================
# 3. Agent 交互接口 (心跳/回调)
# ==========================================

class AgentInfo(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(info: AgentInfo):
    """Agent 上报网卡状态"""
    c2_state['interfaces'] = info.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "registered"}


@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Agent 领取任务"""
    c2_state['last_heartbeat'] = time.time()
    if c2_state['current_task'] != 'idle':
        return {
            "status": "ok",
            "task": c2_state['current_task'],
            "params": c2_state['task_params']
        }
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    type: str
    networks: Optional[List[Dict]] = None
    data: Optional[List[Dict]] = None


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    """接收 Agent 数据"""

    # 普通扫描回调
    if payload.type == 'scan_result' and payload.networks is not None:
        c2_state['networks'] = payload.networks
        c2_state['current_task'] = 'idle'
        scan_complete_event.set()  # 解锁扫描等待
        return {"status": "received"}

    # 监听数据回调 (入库)
    if payload.type == 'monitor_update' and payload.data:
        target_bssid = c2_state['task_params'].get('bssid')
        for item in payload.data:
            client_mac = item.get('mac')
            if not client_mac: continue

            existing = db.exec(select(TargetedClient).where(
                TargetedClient.client_mac == client_mac,
                TargetedClient.network_bssid == target_bssid
            )).first()

            pkt = int(item.get('packets', 0))
            sig = int(item.get('power', 0))

            if not existing:
                db.add(TargetedClient(
                    network_bssid=target_bssid,
                    client_mac=client_mac,
                    packet_count=pkt,
                    signal=sig,
                    last_seen=datetime.utcnow()
                ))
            else:
                existing.packet_count = pkt
                existing.signal = sig
                existing.last_seen = datetime.utcnow()
        db.commit()
        return {"status": "updated"}

    return {"status": "ok"}


# ==========================================
# 4. 前端查询接口
# ==========================================

@router.get("/monitor/clients/{bssid}")
async def get_targeted_clients(bssid: str, db: Session = Depends(get_session)):
    return db.exec(select(TargetedClient).where(TargetedClient.network_bssid == bssid)).all()


@router.get("/monitor/deep_results")
async def get_deep_scan_results(db: Session = Depends(get_session)):
    return db.exec(select(DeepScanClient).order_by(DeepScanClient.last_seen.desc()).limit(100)).all()