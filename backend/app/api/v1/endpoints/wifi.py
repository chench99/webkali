from fastapi import APIRouter, BackgroundTasks, HTTPException, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import asyncio
import os
import time

# 引入 SSH 管理器 (用于自动部署)
from app.core.ssh_manager import ssh_client
# 引入攻击模块
from app.modules.wifi.attacker import WifiAttacker  # 假设你保留了攻击模块逻辑

router = APIRouter()

# ==========================================
# C2 状态存储
# ==========================================
c2_state = {
    "interfaces": [],
    "networks": [],
    "current_task": None,
    "task_params": {},
    "last_heartbeat": 0
}

scan_complete_event = asyncio.Event()


# ==========================================
# 1. 核心功能：SSH 自动部署 Agent (新增)
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

    # 2. 定位 Payload 脚本路径
    base_dir = os.getcwd()
    # 智能查找 (兼容不同启动目录)
    possible_paths = [
        "kali_payloads/wifi_scanner.py",
        "backend/kali_payloads/wifi_scanner.py",
        "../kali_payloads/wifi_scanner.py"
    ]
    local_payload = None
    for p in possible_paths:
        full_path = os.path.join(base_dir, p)
        if os.path.exists(full_path):
            local_payload = full_path
            break

    if not local_payload:
        return {"status": "error", "message": "服务端找不到 wifi_scanner.py 文件"}

    try:
        # 3. 上传脚本
        print(f"[*] 正在上传 Payload: {local_payload}")
        remote_path = ssh_client.upload_payload(local_payload, "wifi_scanner.py")

        if not remote_path:
            return {"status": "error", "message": "SFTP 上传失败"}

        # 4. 自动注入 C2 IP (这是自动化的关键！)
        # 获取本机 IP (Docker 环境可能需要配置外部 IP，这里简单获取)
        # 也可以从 .env 读取 C2_HOST
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)

        # 使用 sed 命令修改脚本里的 IP 配置，免去手动输入
        # 假设脚本里有一行 FIXED_C2_IP = ""
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
# 2. Agent 交互接口 (Kali 调用)
# ==========================================
@router.get("/agent/heartbeat")
async def agent_heartbeat():
    c2_state['last_heartbeat'] = time.time()
    if c2_state['current_task']:
        task = c2_state['current_task']
        params = c2_state['task_params']
        c2_state['current_task'] = None
        c2_state['task_params'] = {}
        print(f"[*] C2 指令下发 -> Agent: {task}")
        return {"status": "ok", "task": task, "params": params}
    return {"status": "ok", "task": "idle"}


class ScanResult(BaseModel):
    interface: str
    count: int
    networks: List[Dict]


@router.post("/callback")
async def receive_scan_result(data: ScanResult):
    print(f"[*] 收到 Agent 回传数据: {data.count} 个目标")
    c2_state['networks'] = data.networks
    scan_complete_event.set()
    return {"status": "received"}


class AgentInfo(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(info: AgentInfo):
    print(f"[*] Agent 上线! 网卡: {[i['display'] for i in info.interfaces]}")
    c2_state['interfaces'] = info.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "registered"}


# ==========================================
# 3. 前端交互接口 (Vue 调用)
# ==========================================
@router.get("/interfaces")
async def get_interfaces():
    # 这里的 Waiting 状态现在会触发前端显示“重连按钮”，而不是下载链接
    is_online = (time.time() - c2_state['last_heartbeat']) < 15
    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "Agent 离线", "is_wireless": False}]}
    return {"interfaces": c2_state['interfaces']}


class ScanReq(BaseModel):
    interface: Optional[str]


@router.post("/scan/start")
async def trigger_scan(req: ScanReq = Body(None)):
    # 检查在线
    if (time.time() - c2_state['last_heartbeat']) > 15:
        return {"code": 500, "message": "Agent 离线，请点击'重连 Agent'"}

    print("[*] 前端发布扫描任务...")
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        await asyncio.wait_for(scan_complete_event.wait(), timeout=15.0)
        msg = "扫描成功"
        status = "success"
    except asyncio.TimeoutError:
        msg = "等待 Agent 响应超时"
        status = "timeout"

    return {
        "code": 200, "status": status, "message": msg,
        "networks": c2_state['networks']
    }


# 攻击接口保持不变
class AttackConfig(BaseModel):
    bssid: str
    channel: int
    attack_type: str = "deauth"


@router.post("/capture/start")
async def start_attack(config: AttackConfig):
    c2_state['current_task'] = 'attack'
    c2_state['task_params'] = {"bssid": config.bssid, "channel": config.channel}
    return {"status": "queued", "message": "攻击指令已下发"}


@router.post("/capture/stop")
async def stop_capture(): return {"status": "ok"}


@router.get("/capture/status")
async def get_status(): return {"is_running": False}