from fastapi import APIRouter, BackgroundTasks, HTTPException, Body, Request
from pydantic import BaseModel
from typing import Optional, List, Dict
import asyncio
import time

# 引入攻击模块 (保留攻击指令下发功能)
from app.modules.wifi.attacker import WifiAttacker

router = APIRouter()
wifi_attacker = WifiAttacker(interface="wlan0mon")

# ==========================================
# C2 数据存储 (内存)
# ==========================================
# 用于暂存 Kali 回传的扫描结果
wifi_data_store = {
    "last_updated": 0,
    "interface": "Unknown",
    "networks": []
}

# 信号量，用于前端等待数据回传
scan_complete_event = asyncio.Event()


# ==========================================
# 1. Kali 回传接口 (C2 Callback)
# ==========================================
class WifiScanResult(BaseModel):
    interface: Optional[str]
    count: int
    networks: List[Dict]
    timestamp: float


@router.post("/callback")
async def receive_kali_data(data: WifiScanResult):
    """
    [C2] 接收 Kali Payload 回传的扫描数据
    """
    global wifi_data_store
    print(f"[*] 收到 Kali 回传数据: {data.count} 个目标 (接口: {data.interface})")

    wifi_data_store["interface"] = data.interface
    wifi_data_store["networks"] = data.networks
    wifi_data_store["last_updated"] = time.time()

    # 通知等待的前端：数据到了
    scan_complete_event.set()

    return {"status": "received", "processed": True}


# ==========================================
# 2. 前端交互接口 (Frontend API)
# ==========================================

@router.get("/interfaces")
async def get_interfaces():
    """
    获取网卡列表
    注意：因为后端在 Windows，这里应该返回 Kali 上传的网卡信息
    如果还没连上 Kali，暂时返回空或提示信息
    """
    # 这里应该从 Agent 心跳包里取，暂时模拟一下，或者让前端提示用户去 Kali 跑脚本
    # 为了不报错，返回一个提示用的假网卡，提示用户连接 C2
    return {
        "interfaces": [
            {
                "name": "Waiting for Kali...",
                "is_wireless": True,
                "mode": "C2 Agent",
                "is_up": True
            }
        ]
    }


class ScanRequest(BaseModel):
    interface: Optional[str] = None


@router.post("/scan/start")
@router.post("/networks")
@router.get("/scan/start")
@router.get("/networks")
async def trigger_scan(req: ScanRequest = Body(default=None)):
    """
    前端点击扫描 -> 触发逻辑
    """
    # 1. 重置信号量
    scan_complete_event.clear()

    print("[*] 前端请求扫描，正在等待 Kali 回传数据...")

    # TODO: 在这里通过 Websocket 或 MQTT 下发指令给 Kali Agent
    # 如果你没有全自动 Agent，你需要手动在 Kali 运行 `python wifi_scanner.py`

    # 2. 等待数据回传 (最多等 10 秒)
    # 如果你是手动跑脚本，前端会在这里卡住，直到你脚本跑完回传
    try:
        await asyncio.wait_for(scan_complete_event.wait(), timeout=10.0)
        status = "success"
        msg = "扫描成功 (来自 Kali)"
    except asyncio.TimeoutError:
        status = "timeout"
        msg = "等待 Kali 响应超时 (请确认 Agent 在线或手动运行 Payload)"
        # 超时了也返回旧数据，防止前端白板

    # 3. 返回存储的数据
    results = wifi_data_store["networks"]

    # 排序
    results.sort(key=lambda x: x.get('signal', -100), reverse=True)

    return {
        "code": 200,
        "status": status,
        "message": msg,
        "interface": wifi_data_store["interface"],
        "count": len(results),
        "networks": results
    }


# ==========================================
# 3. 攻击接口 (指令下发)
# ==========================================
class AttackConfig(BaseModel):
    bssid: str
    channel: int
    attack_type: str = "deauth"


@router.post("/capture/start")
async def start_capture(config: AttackConfig, background_tasks: BackgroundTasks):
    # C2 模式下，这里应该是下发攻击指令给 Kali
    print(f"[*] 下发攻击指令 -> BSSID: {config.bssid}")
    # background_tasks.add_task(...) # 发送给 Agent
    return {"status": "started", "message": "攻击指令已下发至 Kali"}


@router.post("/capture/stop")
async def stop_capture():
    return {"status": "stopped"}


@router.get("/capture/status")
async def get_status():
    return {"is_running": False, "handshake_captured": False}