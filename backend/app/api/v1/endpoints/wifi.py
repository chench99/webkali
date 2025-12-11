from fastapi import APIRouter, BackgroundTasks, HTTPException, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import asyncio
import os
import time

router = APIRouter()

# ==========================================
# C2 状态存储 (内存数据库)
# ==========================================
c2_state = {
    "interfaces": [],  # Agent 上报的网卡
    "networks": [],  # 扫描结果缓存
    "current_task": None,  # 待分发任务 (None / 'scan' / 'attack')
    "task_params": {},  # 任务参数
    "last_heartbeat": 0  # Agent 最后活跃时间
}

# 异步信号量：用于前端阻塞等待扫描结果
scan_complete_event = asyncio.Event()


# ==========================================
# 1. Agent 交互接口 (供 Kali 调用)
# ==========================================

# [A] 心跳接口 (Kali 轮询)
@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Kali Agent 报告存活 + 领取任务"""
    c2_state['last_heartbeat'] = time.time()

    # 检查任务队列
    if c2_state['current_task']:
        task = c2_state['current_task']
        params = c2_state['task_params']

        # 任务领取即清除 (防止重复执行)
        c2_state['current_task'] = None
        c2_state['task_params'] = {}

        print(f"[*] C2 指令下发 -> Agent: {task}")
        return {"status": "ok", "task": task, "params": params}

    return {"status": "ok", "task": "idle"}


# [B] 数据回传接口
class ScanResult(BaseModel):
    interface: str
    count: int
    networks: List[Dict]


@router.post("/callback")
async def receive_scan_result(data: ScanResult):
    print(f"[*] 收到 Agent 回传数据: {data.count} 个目标 (接口: {data.interface})")

    # 可以在这里做二次处理 (比如补充 OUI 厂商信息)
    c2_state['networks'] = data.networks

    # 触发信号，通知前端请求解除阻塞
    scan_complete_event.set()
    return {"status": "received"}


# [C] Agent 注册接口
class AgentInfo(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(info: AgentInfo):
    print(f"[*] Agent 上线! 上报网卡: {[i['display'] for i in info.interfaces]}")
    c2_state['interfaces'] = info.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "registered"}


# [D] Payload 下载接口
@router.get("/payload.py")
async def download_payload():
    """提供脚本下载，方便 Kali 一键部署"""
    # 智能查找路径
    base_dir = os.getcwd()
    possible_paths = [
        "kali_payloads/wifi_scanner.py",
        "backend/kali_payloads/wifi_scanner.py",
        "../kali_payloads/wifi_scanner.py"
    ]

    for p in possible_paths:
        full_path = os.path.join(base_dir, p)
        if os.path.exists(full_path):
            return FileResponse(full_path, filename="wifi_scanner.py")

    return {"error": "Payload file not found on server"}


# ==========================================
# 2. 前端交互接口 (Vue 调用)
# ==========================================

# [A] 获取网卡列表
@router.get("/interfaces")
async def get_interfaces():
    # 判断 Agent 是否在线 (超时 10 秒视为离线)
    is_online = (time.time() - c2_state['last_heartbeat']) < 10

    if not c2_state['interfaces'] or not is_online:
        # 返回一个虚拟的提示网卡，告知用户去运行脚本
        return {"interfaces": [
            {"name": "waiting", "display": "等待 Agent 接入... (请下载脚本运行)", "is_wireless": False,
             "mode": "Offline"}]}

    return {"interfaces": c2_state['interfaces']}


# [B] 触发扫描 (C2 核心逻辑)
class ScanReq(BaseModel):
    interface: Optional[str]


@router.post("/scan/start")
async def trigger_scan(req: ScanReq = Body(None)):
    """前端点击扫描 -> 写入任务 -> 等待 Agent 回传"""

    # 1. 检查在线状态
    if (time.time() - c2_state['last_heartbeat']) > 15:
        return {
            "code": 500,
            "status": "error",
            "message": "Agent 离线！请在 Kali 中运行 payload.py"
        }

    # 2. 重置信号量，发布任务
    print(f"[*] 前端请求扫描，目标接口: {req.interface}")
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    # 3. 阻塞等待 (最多 15 秒)
    try:
        await asyncio.wait_for(scan_complete_event.wait(), timeout=15.0)
        msg = "扫描成功"
        status = "success"
    except asyncio.TimeoutError:
        msg = "扫描超时 (Agent 未及时回传数据)"
        status = "timeout"
        # 超时也返回旧数据，防止前端空白

    return {
        "code": 200,
        "status": status,
        "message": msg,
        "networks": c2_state['networks']
    }


# [C] 攻击接口
class AttackConfig(BaseModel):
    bssid: str
    channel: int
    attack_type: str = "deauth"


@router.post("/capture/start")
async def start_attack(config: AttackConfig):
    print(f"[*] 发布攻击任务 -> {config.bssid}")
    c2_state['current_task'] = 'attack'
    c2_state['task_params'] = {
        "bssid": config.bssid,
        "channel": config.channel,
        "interface": "wlan0"  # 默认，或者从前端传
    }
    return {"status": "queued", "message": "攻击指令已下发"}


# 兼容接口
@router.post("/capture/stop")
async def stop_capture(): return {"status": "ok"}


@router.get("/capture/status")
async def get_status(): return {"is_running": False}