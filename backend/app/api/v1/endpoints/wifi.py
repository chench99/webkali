from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select, delete
from app.core.database import get_session
from app.models.wifi import WiFiNetwork, TargetedClient
from app.core.ssh_manager import ssh_client
from pydantic import BaseModel
from typing import List, Dict, Optional
import time
import os
import asyncio
import socket
from datetime import datetime
from pathlib import Path

router = APIRouter()

# --- C2 状态机 (仅保留轻量级状态) ---
c2_state = {
    "interfaces": [],  # 网卡列表
    "current_task": "idle",  # 当前任务
    "task_params": {},
    "last_heartbeat": 0
}

# 扫描完成事件
scan_complete_event = asyncio.Event()


# ==========================================
# 1. 部署与连接 (保留之前的智能修复版)
# ==========================================
@router.post("/agent/deploy")
async def deploy_agent_via_ssh():
    """[C2] 智能部署 Agent 到 Kali"""
    print(f"\n[DEBUG] ========== 开始部署 Agent ==========")
    if not ssh_client.client:
        ssh_client.connect()
        if not ssh_client.client:
            return {"status": "error", "message": "SSH 连接失败"}

    # 智能查找路径
    current_file = Path(__file__).resolve()
    possible_paths = [
        current_file.parents[5] / "kali_payloads" / "wifi_scanner.py",
        current_file.parents[4] / "kali_payloads" / "wifi_scanner.py",
        Path("kali_payloads/wifi_scanner.py").resolve()
    ]
    payload_src = next((p for p in possible_paths if p.exists()), None)

    if not payload_src:
        return {"status": "error", "message": "服务端找不到 wifi_scanner.py"}

    try:
        remote_path = "/tmp/wifi_scanner.py"
        ssh_client.upload_payload(str(payload_src), "wifi_scanner.py")

        # 注入IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80)); local_ip = s.getsockname()[0]
        except:
            local_ip = "127.0.0.1"
        finally:
            s.close()

        ssh_client.exec_command(f"sed -i 's/FIXED_C2_IP = \"\"/FIXED_C2_IP = \"{local_ip}\"/g' {remote_path}")
        ssh_client.exec_command("pkill -f wifi_scanner.py")
        time.sleep(1)
        ssh_client.exec_command(f"nohup python3 {remote_path} > /tmp/agent.log 2>&1 &")

        return {"status": "success", "message": f"Agent 已部署并启动 (C2: {local_ip})"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/interfaces")
async def get_interfaces():
    is_online = (time.time() - c2_state['last_heartbeat']) < 15
    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "等待 Agent 连接...", "mode": "-"}]}
    return {"interfaces": c2_state['interfaces']}


# ==========================================
# 2. 核心业务逻辑 (持久化改造)
# ==========================================

class ScanReq(BaseModel):
    interface: str = "wlan0"


@router.post("/scan/start")
async def trigger_scan(req: ScanReq, db: Session = Depends(get_session)):
    """
    启动扫描：清空旧数据 -> 下发任务 -> 等待完成
    """
    print(f"[*] [SCAN] 启动新一轮扫描，正在清空数据库...")

    # 1. 数据库重置 (核心需求)
    db.exec(delete(WiFiNetwork))
    db.exec(delete(TargetedClient))
    db.commit()

    # 2. 下发任务
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        # 等待 Agent 回传 (25秒超时)
        await asyncio.wait_for(scan_complete_event.wait(), timeout=25.0)

        # 3. 从数据库读取结果返回
        networks = db.exec(select(WiFiNetwork).order_by(WiFiNetwork.signal_dbm.desc())).all()
        return {"status": "success", "count": len(networks)}

    except asyncio.TimeoutError:
        c2_state['current_task'] = 'idle'
        return {"status": "timeout", "message": "扫描超时"}


@router.get("/networks")
async def get_networks_db(db: Session = Depends(get_session)):
    """从数据库获取 WiFi 列表"""
    return db.exec(select(WiFiNetwork).order_by(WiFiNetwork.signal_dbm.desc())).all()


class MonitorReq(BaseModel):
    bssid: str
    channel: int
    interface: str = "wlan0"


@router.post("/monitor/start")
async def start_monitor(req: MonitorReq):
    print(f"[*] [MONITOR] 锁定目标: {req.bssid}")
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = req.dict()
    return {"status": "queued"}


@router.post("/monitor/stop")
async def stop_monitor():
    c2_state['current_task'] = 'idle'
    return {"status": "stopped"}


@router.get("/monitor/clients/{bssid}")
async def get_monitored_clients(bssid: str, db: Session = Depends(get_session)):
    """从数据库获取特定 AP 的客户端"""
    return db.exec(select(TargetedClient).where(TargetedClient.network_bssid == bssid)).all()


# ==========================================
# 3. Agent 回调 (数据入库)
# ==========================================

class AgentRegister(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(data: AgentRegister):
    c2_state['interfaces'] = data.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "ok"}


@router.get("/agent/heartbeat")
async def agent_heartbeat():
    c2_state['last_heartbeat'] = time.time()
    if c2_state['current_task'] != 'idle':
        return {"status": "ok", "task": c2_state['current_task'], "params": c2_state['task_params']}
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    type: str
    networks: Optional[List[Dict]] = None
    data: Optional[List[Dict]] = None


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    # === A. 处理扫描结果 (批量入库) ===
    if payload.type == 'scan_result' and payload.networks:
        print(f"[*] [CALLBACK] 收到 {len(payload.networks)} 个 AP 数据")

        for net in payload.networks:
            # 简单的 Upsert 逻辑
            existing = db.exec(select(WiFiNetwork).where(WiFiNetwork.bssid == net['bssid'])).first()
            if existing:
                existing.signal_dbm = net.get('signal', -100)
                existing.client_count = net.get('client_count', 0)
                existing.last_seen = datetime.utcnow()
                db.add(existing)
            else:
                new_net = WiFiNetwork(
                    bssid=net['bssid'],
                    ssid=net.get('ssid', '<Hidden>'),
                    channel=net.get('channel', 0),
                    signal_dbm=net.get('signal', -100),
                    encryption=net.get('encryption', 'OPEN'),
                    vendor=net.get('vendor', 'Unknown'),
                    client_count=net.get('client_count', 0)
                )
                db.add(new_net)

        db.commit()
        # 通知等待的接口
        scan_complete_event.set()
        c2_state['current_task'] = 'idle'
        return {"status": "persisted"}

    # === B. 处理监听客户端 (实时入库) ===
    if payload.type == 'monitor_update' and payload.data:
        target = c2_state['task_params'].get('bssid')
        if not target: return {"status": "ignored"}

        count = 0
        for item in payload.data:
            mac = item.get('mac')
            if not mac: continue

            client = db.exec(select(TargetedClient).where(
                TargetedClient.client_mac == mac,
                TargetedClient.network_bssid == target
            )).first()

            pkt = int(item.get('packets', 0))
            sig = int(item.get('signal', -100))

            if client:
                client.packet_count = pkt
                client.signal_dbm = sig
                client.last_seen = datetime.utcnow()
                db.add(client)
            else:
                db.add(TargetedClient(
                    network_bssid=target,
                    client_mac=mac,
                    packet_count=pkt,
                    signal_dbm=sig
                ))
            count += 1

        db.commit()
        # print(f"[*] [CALLBACK] 更新 {count} 个客户端数据")
        return {"status": "updated"}

    return {"status": "ok"}