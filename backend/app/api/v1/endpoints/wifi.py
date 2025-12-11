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

router = APIRouter()

# --- C2 状态机 (内存) ---
c2_state = {
    "interfaces": [],  # Agent 上报的网卡列表
    "current_task": None,  # 当前任务: 'scan', 'monitor_target', 'deep_scan'
    "task_params": {},  # 任务参数
    "last_heartbeat": 0,  # 上次心跳时间
    "networks": []  # 普通扫描结果缓存
}

scan_complete_event = asyncio.Event()


# ==========================================
# 1. 核心修复：一键部署接口 (之前遗漏的！)
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

    # 2. 智能定位 Payload 脚本路径 (修复路径查找问题)
    # 无论你在 backend 目录还是根目录启动，都能找到
    base_path = Path(__file__).resolve().parent.parent.parent.parent.parent  # 回退到项目根目录
    payload_path = base_path / "kali_payloads" / "wifi_scanner.py"

    if not payload_path.exists():
        # 尝试另一种常见路径结构 (开发环境/Docker环境差异)
        payload_path = Path("kali_payloads/wifi_scanner.py")

    if not payload_path.exists():
        return {"status": "error", "message": f"服务端找不到 wifi_scanner.py 文件，路径: {payload_path}"}

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

        # 获取 Docker 宿主机 IP (如果是 Docker 环境)
        if local_ip.startswith("127."):
            # 尝试获取局域网 IP
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
        # 先杀掉旧进程防止冲突
        ssh_client.exec_command("pkill -f wifi_scanner.py")

        cmd = f"nohup python3 {remote_path} > /tmp/agent.log 2>&1 &"
        print(f"[*] 执行启动命令: {cmd}")
        ssh_client.exec_command(cmd)

        return {"status": "success", "message": "Agent 已通过 SSH 启动，请等待心跳上线..."}

    except Exception as e:
        print(f"[!] 部署异常: {e}")
        return {"status": "error", "message": str(e)}


# ==========================================
# 2. 核心修复：获取网卡接口 (之前遗漏的！)
# ==========================================
@router.get("/interfaces")
async def get_interfaces():
    """前端获取 Agent 网卡列表"""
    # 简单的在线状态判断 (15秒无心跳视为离线)
    is_online = (time.time() - c2_state['last_heartbeat']) < 15

    if not c2_state['interfaces'] or not is_online:
        # 返回 waiting 状态，前端会根据这个显示“重连”按钮
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

    # 清空旧数据
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
    """普通列表扫描"""
    print("[*] C2 指令: 普通扫描")
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        await asyncio.wait_for(scan_complete_event.wait(), timeout=15.0)
        return {"status": "success", "networks": c2_state['networks']}
    except asyncio.TimeoutError:
        return {"status": "timeout", "message": "扫描超时"}


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
    print(f"[*] Agent 上线! 网卡: {[i['display'] for i in info.interfaces]}")
    c2_state['interfaces'] = info.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "registered"}


@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Agent 领取任务"""
    c2_state['last_heartbeat'] = time.time()
    if c2_state['current_task']:
        return {
            "status": "ok",
            "task": c2_state['current_task'],
            "params": c2_state['task_params']
        }
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    # 兼容多种回调格式
    type: Optional[str] = None  # 'scan_result', 'monitor_update', 'deep_update'
    interface: Optional[str] = None
    count: Optional[int] = 0
    networks: Optional[List[Dict]] = None
    data: Optional[List[Dict]] = None  # 新版数据字段


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    """接收 Agent 数据"""

    # A. 普通扫描回调
    if payload.networks is not None:
        c2_state['networks'] = payload.networks
        scan_complete_event.set()
        return {"status": "received"}

    # B. 监听/深度扫描回调
    if payload.data:
        # 1. 定向监听数据入库
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
            db.commit()

        # 2. 深度扫描数据入库
        elif payload.type == 'deep_update':
            for item in payload.data:
                client_mac = item.get('mac')
                if not client_mac: continue

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