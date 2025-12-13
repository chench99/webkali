from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select, delete
from app.core.database import get_session
from app.models.wifi import WiFiNetwork, TargetedClient, DeepScanClient
from app.core.ssh_manager import ssh_client
from pydantic import BaseModel
from typing import List, Dict, Optional
import time
import os
import asyncio
from pathlib import Path
from datetime import datetime

router = APIRouter()

# --- C2 状态机 (内存) ---
c2_state = {
    "interfaces": [],  # Agent 上报的网卡列表
    "current_task": "idle",  # 当前任务: 'idle', 'scan', 'monitor_target', 'deep_scan'
    "task_params": {},  # 任务参数
    "last_heartbeat": 0,  # 上次心跳时间
    "networks": []  # 普通扫描结果缓存 (Array of Dict)
}

# 异步事件锁，用于扫描时的同步等待
scan_complete_event = asyncio.Event()


# ==========================================
# 1. 核心修复：一键部署接口 (增强路径查找)
# ==========================================
@router.post("/agent/deploy")
async def deploy_agent_via_ssh():
    """
    [C2] 远程部署接口
    当 Agent 离线时，前端调用此接口，后端通过 SSH 强制重新部署并启动 Agent
    """
    print("[*] 收到 Agent 部署指令，正在连接 SSH...")

    # 1. 建立 SSH 连接
    if not ssh_client.client:
        ssh_client.connect()
        if not ssh_client.client:
            return {"status": "error", "message": "SSH 连接失败，请检查 .env 配置或网络"}

    # 2. 智能定位 Payload 脚本路径
    current_file = Path(__file__).resolve()
    # 向上寻找项目根目录 (根据你的目录结构，可能需要调整层级)
    # 假设结构: WebKali/backend/app/api/v1/endpoints/wifi.py
    # 我们要找: WebKali/backend/kali_payloads/wifi_scanner.py
    # 或者 WebKali/kali_payloads/wifi_scanner.py

    # 优先尝试 backend 同级目录
    possible_paths = [
        current_file.parents[5] / "kali_payloads" / "wifi_scanner.py",  # Project Root
        current_file.parents[4] / "kali_payloads" / "wifi_scanner.py",  # Backend Root
        Path.cwd() / "kali_payloads" / "wifi_scanner.py",  # CWD
        Path.cwd().parent / "kali_payloads" / "wifi_scanner.py"
    ]

    payload_path = None
    for p in possible_paths:
        if p.exists():
            payload_path = p
            print(f"[DEBUG] 成功定位 Payload: {payload_path}")
            break

    if not payload_path:
        return {"status": "error", "message": f"服务端找不到 wifi_scanner.py。请检查 kali_payloads 目录。"}

    try:
        # 3. 上传脚本
        print(f"[*] 正在上传 Payload: {payload_path}")
        remote_path = ssh_client.upload_payload(str(payload_path), "wifi_scanner.py")

        if not remote_path:
            return {"status": "error", "message": "SFTP 上传失败"}

        # 4. 自动注入 C2 IP (这是自动化的关键！)
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        # 增强获取 IP 逻辑 (Docker/虚拟机环境下 localhost 可能不对)
        if local_ip.startswith("127."):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except:
                pass

        print(f"[*] 注入 C2 IP: {local_ip}")
        # 使用 sed 修改脚本中的配置
        ssh_client.exec_command(f"sed -i 's/FIXED_C2_IP = \"\"/FIXED_C2_IP = \"{local_ip}\"/g' {remote_path}")

        # 5. 启动进程 (nohup 后台运行)
        ssh_client.exec_command("pkill -f wifi_scanner.py")  # 杀掉旧进程
        cmd = f"nohup python3 {remote_path} > /tmp/agent.log 2>&1 &"
        print(f"[*] 执行启动命令: {cmd}")
        ssh_client.exec_command(cmd)

        return {"status": "success", "message": "Agent 已通过 SSH 启动，请等待心跳上线..."}

    except Exception as e:
        print(f"[!] 部署异常: {e}")
        return {"status": "error", "message": str(e)}


# ==========================================
# 2. 核心修复：获取网卡接口
# ==========================================
@router.get("/interfaces")
async def get_interfaces():
    """前端获取 Agent 网卡列表"""
    # 简单的在线状态判断 (15秒无心跳视为离线)
    is_online = (time.time() - c2_state['last_heartbeat']) < 15

    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "Agent 离线", "is_wireless": False}]}

    return {"interfaces": c2_state['interfaces']}


# ==========================================
# 3. 任务控制接口 (监听/扫描/停止)
# ==========================================

class MonitorReq(BaseModel):
    bssid: str
    channel: int


@router.post("/monitor/start")
async def start_target_monitor(req: MonitorReq):
    """启动定向监听"""
    print(f"[*] C2 指令: 锁定监听 {req.bssid} (CH {req.channel})")
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = {
        'bssid': req.bssid,
        'channel': req.channel
    }
    return {"status": "queued", "msg": "监听指令已进入队列"}


@router.post("/monitor/deep")
async def start_deep_scan(db: Session = Depends(get_session)):
    """启动深度全网扫描 (先清空表)"""
    print("[*] C2 指令: 开启全网深度扫描")
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
    """
    [C2] 触发普通扫描
    注意：这里不会直接执行扫描，而是设置状态，等待 Agent 领取任务并回调。
    """
    print("[*] C2 指令: 普通扫描请求")

    # 1. 重置事件
    scan_complete_event.clear()

    # 2. 设置 C2 状态，等待 Agent 心跳领取
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        # 3. 阻塞等待 Agent 回调 (最长等待 20 秒)
        print("[*] 等待 Agent 回传扫描结果...")
        await asyncio.wait_for(scan_complete_event.wait(), timeout=20.0)

        # 4. 收到结果，返回给前端
        print(f"[*] 扫描完成，返回 {len(c2_state['networks'])} 个结果")
        return {"status": "success", "networks": c2_state['networks']}

    except asyncio.TimeoutError:
        print("[!] 扫描超时")
        c2_state['current_task'] = 'idle'  # 超时重置
        return {"status": "timeout", "message": "Agent 响应超时，请检查连接"}


@router.get("/networks")
async def get_networks_cache():
    """获取普通扫描的缓存结果"""
    return c2_state['networks']


# ==========================================
# 4. Agent 交互接口 (心跳与回调)
# ==========================================

class AgentInfo(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(info: AgentInfo):
    # print(f"[*] Agent 上线/心跳: {[i['display'] for i in info.interfaces]}")
    c2_state['interfaces'] = info.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "registered"}


@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Agent 领取任务 (Polling)"""
    c2_state['last_heartbeat'] = time.time()

    # 如果有任务，分发给 Agent
    if c2_state['current_task'] != 'idle':
        return {
            "status": "ok",
            "task": c2_state['current_task'],
            "params": c2_state['task_params']
        }
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    type: str  # 'scan_result', 'monitor_update', 'deep_update'
    networks: Optional[List[Dict]] = None  # 普通扫描结果
    data: Optional[List[Dict]] = None  # 监听结果


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    """接收 Agent 数据"""

    # A. 处理普通扫描结果
    if payload.type == 'scan_result' and payload.networks is not None:
        print(f"[*] 收到 Agent 扫描结果: {len(payload.networks)} 个网络")
        c2_state['networks'] = payload.networks
        c2_state['current_task'] = 'idle'  # 扫描是一次性任务，完成后重置
        scan_complete_event.set()  # 解锁 trigger_scan 的等待
        return {"status": "received"}

    # B. 处理监听数据 (Target Monitor / Deep Scan)
    if payload.data:
        # 1. 定向监听入库
        if payload.type == 'monitor_update':
            bssid = c2_state['task_params'].get('bssid')
            for item in payload.data:
                client_mac = item.get('mac')
                if not client_mac: continue

                existing = db.exec(select(TargetedClient).where(
                    TargetedClient.client_mac == client_mac,
                    TargetedClient.network_bssid == bssid
                )).first()

                if not existing:
                    db.add(TargetedClient(
                        network_bssid=bssid,
                        client_mac=client_mac,
                        packet_count=int(item.get('packets', 0)),
                        signal=int(item.get('power', 0))
                    ))
                else:
                    existing.packet_count = int(item.get('packets', 0))
                    existing.signal = int(item.get('power', 0))
                    existing.last_seen = datetime.utcnow()
            db.commit()

        # 2. 深度扫描入库
        elif payload.type == 'deep_update':
            for item in payload.data:
                client_mac = item.get('mac')
                if not client_mac: continue
                # (保持原有逻辑...)
                existing = db.exec(select(DeepScanClient).where(DeepScanClient.client_mac == client_mac)).first()
                if not existing:
                    db.add(DeepScanClient(
                        client_mac=client_mac,
                        connected_bssid=item.get('bssid'),
                        probed_essids=item.get('probed'),
                        signal=int(item.get('power', 0)),
                        capture_channel=item.get('channel', 0)
                    ))
                else:
                    new_probed = item.get('probed')
                    if new_probed and len(new_probed) > len(existing.probed_essids or ""):
                        existing.probed_essids = new_probed
                    existing.signal = int(item.get('power', 0))
                    if item.get('channel'):
                        existing.capture_channel = int(item.get('channel'))
                    existing.last_seen = datetime.utcnow()
            db.commit()

    return {"status": "received"}


# ==========================================
# 5. 前端数据查询接口
# ==========================================
@router.get("/monitor/clients/{bssid}")
async def get_targeted_clients(bssid: str, db: Session = Depends(get_session)):
    return db.exec(select(TargetedClient).where(TargetedClient.network_bssid == bssid)).all()


@router.get("/monitor/deep_results")
async def get_deep_scan_results(db: Session = Depends(get_session)):
    return db.exec(select(DeepScanClient).order_by(DeepScanClient.last_seen.desc()).limit(100)).all()