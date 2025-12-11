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
    "interfaces": [],  # Agent 网卡列表
    "networks": [],  # 扫描结果
    "current_task": None,  # 当前待执行的任务 (None / 'scan' / 'attack')
    "task_params": {},  # 任务参数 (如攻击哪个BSSID)
    "last_heartbeat": 0  # Agent 最后心跳时间
}

# 异步信号量：用于前端等待扫描完成
scan_complete_event = asyncio.Event()


# ==========================================
# 1. Agent 专用接口 (供 Kali 调用)
# ==========================================

# [A] 心跳与任务领取接口 (Kali 每秒访问一次这里)
@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Kali Agent 轮询接口：报告存活 + 领取任务"""
    c2_state['last_heartbeat'] = time.time()

    # 检查是否有待执行的任务
    if c2_state['current_task']:
        task = c2_state['current_task']
        params = c2_state['task_params']

        # 任务领取后，清除队列中的任务，防止重复执行
        # (也可以设计为 Agent 执行完再清除，这里简化逻辑)
        c2_state['current_task'] = None
        c2_state['task_params'] = {}

        print(f"[*] 指令下发给 Agent: {task}")
        return {"status": "ok", "task": task, "params": params}

    return {"status": "ok", "task": "idle"}  # 无任务，待机


# [B] 接收扫描结果接口
class ScanResult(BaseModel):
    interface: str
    count: int
    networks: List[Dict]


@router.post("/callback")
async def receive_scan_result(data: ScanResult):
    print(f"[*] 收到 Agent 扫描数据: {data.count} 个目标")
    c2_state['networks'] = data.networks
    # 通知前端：扫描完成！
    scan_complete_event.set()
    return {"status": "received"}


# [C] Agent 注册/更新网卡接口
class AgentInfo(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(info: AgentInfo):
    print(f"[*] Agent 上线/更新网卡: {[i['display'] for i in info.interfaces]}")
    c2_state['interfaces'] = info.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "registered"}


# [D] 脚本下载接口
@router.get("/payload.py")
async def download_payload():
    """提供 Payload 下载"""
    # 自动查找文件路径
    base_dir = os.getcwd()
    possible_paths = [
        "app/../kali_payloads/wifi_scanner.py",
        "kali_payloads/wifi_scanner.py",
        "backend/kali_payloads/wifi_scanner.py"
    ]
    for p in possible_paths:
        full_path = os.path.join(base_dir, p)
        if os.path.exists(full_path):
            return FileResponse(full_path, filename="wifi_scanner.py")
    return {"error": "Payload file not found"}


# ==========================================
# 2. 前端 专用接口 (Vue 调用)
# ==========================================

@router.get("/interfaces")
async def get_interfaces():
    """前端获取网卡列表"""
    # 检查 Agent 是否在线 (超过 10 秒没心跳视为离线)
    is_online = (time.time() - c2_state['last_heartbeat']) < 10

    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "等待 Agent 接入... (请运行脚本)", "is_wireless": False}]}

    return {"interfaces": c2_state['interfaces']}


class ScanReq(BaseModel):
    interface: Optional[str]


@router.post("/scan/start")
async def trigger_scan(req: ScanReq = Body(None)):
    """前端点击扫描 -> 发布任务 -> 等待结果"""
    # 1. 检查 Agent 是否在线
    if (time.time() - c2_state['last_heartbeat']) > 15:
        return {"code": 500, "message": "Agent 离线！请在 Kali 重新运行 payload.py"}

    # 2. 发布任务到队列
    print("[*] 前端发布扫描任务...")
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    # 3. 阻塞等待 Agent 回传 (最多等 15 秒)
    try:
        await asyncio.wait_for(scan_complete_event.wait(), timeout=15.0)
        msg = "扫描成功"
        status = "success"
    except asyncio.TimeoutError:
        msg = "扫描超时 (Agent 未及时响应)"
        status = "timeout"
        # 即使超时也把旧数据返回去，避免前端报错

    return {
        "code": 200,
        "status": status,
        "message": msg,
        "networks": c2_state['networks']
    }


# 攻击指令下发
class AttackConfig(BaseModel):
    bssid: str
    channel: int
    attack_type: str = "deauth"


@router.post("/capture/start")
async def start_attack(config: AttackConfig):
    # 将攻击指令放入任务队列
    print(f"[*] 发布攻击任务 -> {config.bssid}")
    c2_state['current_task'] = 'attack'
    c2_state['task_params'] = {
        "bssid": config.bssid,
        "channel": config.channel,
        "type": config.attack_type
    }
    return {"status": "queued", "message": "攻击指令已进入队列，等待 Agent 执行"}


# 兼容接口
@router.post("/capture/stop")
async def stop_cap(): return {"status": "ok"}


@router.get("/capture/status")
async def get_stat(): return {"is_running": False}


@router.get("/system/status")
async def sys_status(): return {"online_users": 1, "cpu_percent": 10}  # 简化的系统状态