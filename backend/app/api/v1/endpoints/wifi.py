from fastapi import APIRouter, BackgroundTasks, HTTPException, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import asyncio
import os

router = APIRouter()

# 内存数据库
c2_state = {
    "interfaces": [],  # 存 Kali 发来的真实网卡
    "networks": [],  # 存扫描结果
    "last_seen": None
}
scan_event = asyncio.Event()


# ==========================================
# 1. 脚本分发接口 (让 Kali 下载)
# ==========================================
@router.get("/payload.py")
async def download_payload():
    """提供 Payload 脚本下载"""
    # 假设文件在 backend/kali_payloads/wifi_scanner.py
    # 自动定位路径
    base_dir = os.getcwd()
    file_path = os.path.join(base_dir, "app/../kali_payloads/wifi_scanner.py")
    if os.path.exists(file_path):
        return FileResponse(file_path, filename="wifi_scanner.py")
    # 备用路径查找
    file_path = os.path.join(base_dir, "kali_payloads/wifi_scanner.py")
    if os.path.exists(file_path):
        return FileResponse(file_path, filename="wifi_scanner.py")
    return {"error": "Payload file not found on server"}


# ==========================================
# 2. Agent 注册接口 (获取真实网卡)
# ==========================================
class AgentInfo(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(info: AgentInfo):
    """Kali 启动时调用此接口上报网卡"""
    print(f"[*] Kali Agent 上线! 上报网卡: {[i['display'] for i in info.interfaces]}")
    c2_state['interfaces'] = info.interfaces
    c2_state['last_seen'] = "Just now"
    return {"status": "registered"}


# ==========================================
# 3. 扫描数据回传接口
# ==========================================
class ScanResult(BaseModel):
    interface: str
    count: int
    networks: List[Dict]
    timestamp: float


@router.post("/callback")
async def receive_data(data: ScanResult):
    print(f"[*] 收到 Kali 扫描数据: {data.count} 个目标")
    c2_state['networks'] = data.networks
    scan_event.set()
    return {"status": "ok"}


# ==========================================
# 4. 前端接口
# ==========================================
@router.get("/interfaces")
async def get_interfaces_frontend():
    """前端获取 Kali 的网卡"""
    # 如果 Kali 还没连上来，返回空或提示
    if not c2_state['interfaces']:
        return {"interfaces": [{"name": "waiting", "display": "等待 Kali 连接...", "is_wireless": False}]}
    return {"interfaces": c2_state['interfaces']}


class ScanReq(BaseModel):
    interface: Optional[str]


@router.post("/scan/start")
async def trigger_scan(req: ScanReq = Body(None)):
    scan_event.clear()
    # 这里是 HTTP C2 的局限：我们无法主动推给 Kali，只能等 Kali 轮询或者手动触发
    # 为了演示，我们假设用户已经手动在 Kali 执行了脚本
    print("[*] 前端等待数据中...")
    try:
        await asyncio.wait_for(scan_event.wait(), timeout=15.0)
        msg = "扫描成功"
    except:
        msg = "等待超时 (请在 Kali 运行脚本)"

    # 补全 OUI (可选，后端处理比 Payload 处理更好维护)
    # ... (省略重复代码，重点是数据流)

    return {
        "code": 200,
        "networks": c2_state['networks'],
        "message": msg
    }


# 攻击相关保持不变...
@router.post("/capture/start")
async def start_cap(): return {"status": "queued"}


@router.post("/capture/stop")
async def stop_cap(): return {"status": "queued"}


@router.get("/capture/status")
async def get_stat(): return {"is_running": False}