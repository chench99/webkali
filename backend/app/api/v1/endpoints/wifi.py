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
import socket

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
# 1. 核心修复：智能一键部署接口
# ==========================================
@router.post("/agent/deploy")
async def deploy_agent_via_ssh():
    """
    [C2] 远程部署接口
    当 Agent 离线时，前端调用此接口，后端通过 SSH 强制重新部署并启动 Agent
    """
    print("[*] 收到 Agent 部署指令，开始执行...")

    # -------------------------------------------------
    # A. 建立 SSH 连接 (失败则控制台输出)
    # -------------------------------------------------
    if not ssh_client.client:
        print(f"[*] 尝试连接 SSH: {ssh_client.host}...")
        ssh_client.connect()

    if not ssh_client.client:
        msg = f"[!] SSH 连接失败！请检查 .env 配置 (IP: {ssh_client.host}) 或网络连通性。"
        print(msg)  # <--- 控制台输出
        return {"status": "error", "message": msg}

    # -------------------------------------------------
    # B. 智能定位 Payload 脚本路径 (逐级向上查找)
    # -------------------------------------------------
    current_path = Path(__file__).resolve()
    payload_path = None

    # 搜索策略：从当前目录开始，逐级向上找 10 层
    # 寻找目标：任何一层目录下的 'kali_payloads/wifi_scanner.py'
    search_dirs = [current_path.parent] + list(current_path.parents)

    print(f"[*] 开始寻找 Payload，起始路径: {current_path}")

    for directory in search_dirs[:10]:  # 限制回溯层级，防止死循环
        # 检查当前目录下的 kali_payloads
        candidate = directory / "kali_payloads" / "wifi_scanner.py"
        if candidate.exists():
            payload_path = candidate
            break

        # 也可以检查 backend 同级的目录 (开发环境常见结构)
        # 即 directory/../kali_payloads
        candidate_sibling = directory.parent / "kali_payloads" / "wifi_scanner.py"
        if candidate_sibling.exists():
            payload_path = candidate_sibling
            break

    # -------------------------------------------------
    # C. 脚本上传检查 (失败则控制台输出)
    # -------------------------------------------------
    if not payload_path:
        # 构建详细的错误报告
        searched_paths = [str(d) for d in search_dirs[:3]]
        msg = (
            f"[!] 致命错误：无法在服务器上找到 wifi_scanner.py！\n"
            f"    - 已扫描路径: {searched_paths}...\n"
            f"    - 请确认 'kali_payloads' 文件夹是否存在于项目根目录。"
        )
        print(msg)  # <--- 控制台输出
        return {"status": "error", "message": "服务端找不到 wifi_scanner.py 文件 (详情见后端控制台)"}

    print(f"[*] 成功定位 Payload: {payload_path}")

    try:
        # 上传脚本
        remote_filename = "wifi_scanner.py"
        print(f"[*] 正在通过 SFTP 上传...")
        remote_path = ssh_client.upload_payload(str(payload_path), remote_filename)

        if not remote_path:
            msg = "[!] SFTP 上传失败，请检查 SSH 写权限。"
            print(msg)
            return {"status": "error", "message": msg}

        # -------------------------------------------------
        # D. 自动注入 C2 IP (智能获取本机IP)
        # -------------------------------------------------
        # 获取本机 IP 用于 Agent 回连
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 连接外网 IP 不需要真实发送数据，只是为了选路拿到本机内网 IP
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"
        finally:
            s.close()

        print(f"[*] 注入 C2 回连地址: {local_ip}")
        # 使用 sed 修改脚本中的配置
        ssh_client.exec_command(f"sed -i 's/FIXED_C2_IP = \"\"/FIXED_C2_IP = \"{local_ip}\"/g' {remote_path}")

        # -------------------------------------------------
        # E. 启动进程
        # -------------------------------------------------
        # 先杀掉旧进程防止冲突
        ssh_client.exec_command("pkill -f wifi_scanner.py")

        # 启动新进程 (nohup)
        cmd = f"nohup python3 {remote_path} > /tmp/agent.log 2>&1 &"
        print(f"[*] 执行启动命令: {cmd}")
        ssh_client.exec_command(cmd)

        return {"status": "success", "message": f"Agent 已部署并启动! C2 IP: {local_ip}"}

    except Exception as e:
        print(f"[!] 部署过程中发生未知异常: {e}")
        return {"status": "error", "message": str(e)}


# ==========================================
# 2. 获取网卡接口 (保持原样)
# ==========================================
@router.get("/interfaces")
async def get_interfaces():
    """前端获取 Agent 网卡列表"""
    # 15秒无心跳视为离线
    is_online = (time.time() - c2_state['last_heartbeat']) < 15

    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "Agent 离线 / 等待部署...", "is_wireless": False}]}

    return {"interfaces": c2_state['interfaces']}


# ==========================================
# 3. 任务控制接口 (保持原样)
# ==========================================

class MonitorReq(BaseModel):
    bssid: str
    channel: int


@router.post("/monitor/start")
async def start_target_monitor(req: MonitorReq):
    print(f"[*] C2 指令: 锁定监听 {req.bssid} (CH {req.channel})")
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = {
        'bssid': req.bssid,
        'channel': req.channel
    }
    return {"status": "queued", "msg": "监听指令已进入队列"}


@router.post("/monitor/deep")
async def start_deep_scan(db: Session = Depends(get_session)):
    print("[*] C2 指令: 开启全网深度扫描")
    db.exec(delete(DeepScanClient))
    db.commit()
    c2_state['current_task'] = 'deep_scan'
    c2_state['task_params'] = {}
    return {"status": "queued", "msg": "深度扫描已启动"}


@router.post("/monitor/stop")
async def stop_all_tasks():
    c2_state['current_task'] = 'idle'
    c2_state['task_params'] = {}
    return {"status": "stopped"}


class ScanReq(BaseModel):
    interface: Optional[str]


@router.post("/scan/start")
async def trigger_scan(req: ScanReq = Body(None)):
    print("[*] C2 指令: 普通扫描")
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        await asyncio.wait_for(scan_complete_event.wait(), timeout=20.0)  # 延长超时到20秒适配双频扫描
        return {"status": "success", "networks": c2_state['networks']}
    except asyncio.TimeoutError:
        return {"status": "timeout", "message": "扫描超时"}


@router.get("/networks")
async def get_networks_cache():
    return c2_state['networks']


# ==========================================
# 4. Agent 交互接口 (保持原样)
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
    c2_state['last_heartbeat'] = time.time()
    if c2_state['current_task']:
        return {
            "status": "ok",
            "task": c2_state['current_task'],
            "params": c2_state['task_params']
        }
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    type: Optional[str] = None
    interface: Optional[str] = None
    count: Optional[int] = 0
    networks: Optional[List[Dict]] = None
    data: Optional[List[Dict]] = None


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    # A. 普通扫描回调
    if payload.networks is not None:
        c2_state['networks'] = payload.networks
        scan_complete_event.set()
        return {"status": "received"}

    # B. 监听/深度扫描回调
    if payload.data:
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
                    existing.signal = int(item.get('power', 0))
                    if item.get('channel'):
                        existing.capture_channel = int(item.get('channel'))
            db.commit()

    return {"status": "received"}


# ==========================================
# 5. 前端数据查询接口 (保持原样)
# ==========================================

@router.get("/monitor/clients/{bssid}")
async def get_targeted_clients(bssid: str, db: Session = Depends(get_session)):
    return db.exec(select(TargetedClient).where(TargetedClient.network_bssid == bssid)).all()


@router.get("/monitor/deep_results")
async def get_deep_scan_results(db: Session = Depends(get_session)):
    return db.exec(select(DeepScanClient).order_by(DeepScanClient.last_seen.desc()).limit(100)).all()