from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import Session, select, delete
from app.core.database import get_session
from app.models.wifi import WiFiNetwork, TargetedClient
from app.core.ssh_manager import ssh_client
from app.core.config import settings
from pydantic import BaseModel
from typing import List, Dict, Optional
import time
import os
import asyncio
import socket
from datetime import datetime
from pathlib import Path
import re
import json

router = APIRouter()

# ==========================================
# 全局状态与配置
# ==========================================
# C2 状态机
c2_state = {
    "interfaces": [],
    "current_task": "idle",
    "task_params": {},
    "last_heartbeat": 0
}

monitor_state = {
    "last_update": 0.0,
    "last_count": 0,
    "target_bssid": ""
}

scan_complete_event = asyncio.Event()

# 握手包存储路径
_handshake_dir = Path(__file__).resolve().parents[5] / "captures" / "handshakes"
_handshake_dir.mkdir(parents=True, exist_ok=True)


# ==========================================
# 辅助函数
# ==========================================
def _normalize_bssid(value: str) -> str:
    if not value:
        return "unknown"
    v = value.strip().lower()
    if re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", v):
        return v
    return "unknown"


def _detect_local_ip_for_kali() -> str:
    """
    自动探测本机 IP (用于 Kali 回连)
    注意：如果存在虚拟网卡(VMware/Docker)，此函数可能会获取到错误的 IP
    建议在 .env 中配置 C2_HOST 来覆盖此逻辑
    """
    host = getattr(ssh_client, "host", None) or settings.KALI_HOST
    port = getattr(settings, "KALI_PORT", 22)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, port))
        ip = s.getsockname()[0]
        return ip or "127.0.0.1"
    except Exception:
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return ip or "127.0.0.1"
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()


def _safe_int(value, default: int) -> int:
    try:
        if value is None: return default
        if isinstance(value, bool): return int(value)
        if isinstance(value, (int, float)): return int(value)
        s = str(value).strip()
        if not s: return default
        return int(float(s))
    except Exception:
        return default


# ==========================================
# 1. Agent 调试与日志接口
# ==========================================
@router.get("/agent/debug")
async def get_agent_debug():
    now = time.time()
    last = float(c2_state.get("last_heartbeat") or 0)
    return {
        "server_time": int(now),
        "last_heartbeat": int(last) if last else 0,
        "heartbeat_age_sec": round(now - last, 1) if last else None,
        "interfaces_count": len(c2_state.get("interfaces") or []),
        "current_task": c2_state.get("current_task"),
        "task_params": c2_state.get("task_params"),
    }


@router.get("/agent/log")
async def get_agent_log(lines: int = 120):
    if lines < 1: lines = 1
    if lines > 500: lines = 500
    if not ssh_client.client:
        ssh_client.connect()
    if not ssh_client.client:
        raise HTTPException(status_code=503, detail="SSH 未连接，无法读取 Kali 日志")
    stdin, stdout, stderr = ssh_client.exec_command(f"tail -n {int(lines)} /tmp/agent.log || true")
    return {"lines": stdout.read().decode(errors="ignore")}


@router.get("/monitor/debug")
async def get_monitor_debug():
    now = time.time()
    last = float(monitor_state.get("last_update") or 0)
    return {
        "server_time": int(now),
        "target_bssid": monitor_state.get("target_bssid") or "",
        "last_update": int(last) if last else 0,
        "age_sec": round(now - last, 1) if last else None,
        "last_count": int(monitor_state.get("last_count") or 0),
        "current_task": c2_state.get("current_task"),
        "task_params": c2_state.get("task_params"),
    }


# ==========================================
# 2. 握手包管理接口
# ==========================================
@router.post("/handshake/upload")
async def upload_handshake(file: UploadFile = File(...), bssid: str = Form(""), ssid: str = Form("")):
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    ext = Path(filename).suffix.lower()
    if ext not in [".cap", ".pcap", ".pcapng", ".hc22000"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    bssid_norm = _normalize_bssid(bssid)
    ts = int(time.time())
    safe_name = f"handshake_{bssid_norm.replace(':', '')}_{ts}{ext}"
    dst = _handshake_dir / safe_name

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")

    dst.write_bytes(data)
    return {
        "status": "success",
        "filename": safe_name,
        "bssid": bssid_norm,
        "ssid": (ssid or "").strip(),
        "size": dst.stat().st_size
    }


@router.get("/handshake/list")
async def list_handshakes(bssid: str = ""):
    bssid_norm = _normalize_bssid(bssid) if bssid else ""
    items = []
    if _handshake_dir.exists():
        for p in sorted(_handshake_dir.glob("handshake_*"), key=lambda x: x.stat().st_mtime, reverse=True):
            name = p.name
            if bssid_norm and (f"handshake_{bssid_norm.replace(':', '')}_" not in name):
                continue
            st = p.stat()
            items.append({
                "filename": name,
                "size": st.st_size,
                "mtime": int(st.st_mtime)
            })
    return {"items": items}


@router.get("/handshake/download/{filename}")
async def download_handshake(filename: str):
    name = Path(filename).name
    path = _handshake_dir / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(path), filename=name)


# ==========================================
# 3. Agent 智能部署接口 (🔥 已修复 IP 注入)
# ==========================================
@router.post("/agent/deploy")
async def deploy_agent_via_ssh():
    """[C2] 强制重装 Agent 并执行双重健康检查"""
    print(f"\n[DEBUG] ========== 开始部署 Agent ==========")

    # 1. SSH 连接检查
    if not ssh_client.client:
        print(f"[DEBUG] 正在建立 SSH 连接...")
        try:
            ssh_client.connect()
        except Exception as e:
            return {"status": "error", "message": f"SSH 连接失败: {str(e)}"}

    if not ssh_client.client:
        return {"status": "error", "message": "SSH 连接失败"}

    print(f"[DEBUG] ✅ SSH 连接状态正常")

    # 2. 智能定位 Payload
    current_file = Path(__file__).resolve()
    # 尝试多种可能的路径结构 (适配 Docker 和 本地开发)
    possible_paths = [
        current_file.parents[5] / "kali_payloads" / "wifi_scanner.py",
        current_file.parents[4] / "kali_payloads" / "wifi_scanner.py",
        Path("kali_payloads/wifi_scanner.py").resolve(),
    ]

    payload_src = None
    for p in possible_paths:
        if p.exists():
            payload_src = p
            print(f"[DEBUG] ✅ 成功定位 Payload 文件: {p}")
            break

    if not payload_src:
        return {"status": "error", "message": "服务端找不到 wifi_scanner.py"}

    try:
        remote_path = "/tmp/wifi_scanner.py"

        # 3. 上传文件
        print(f"[DEBUG] 正在上传至 Kali: {remote_path}")
        ssh_client.upload_payload(str(payload_src), "wifi_scanner.py")

        # 4. 验证文件
        stdin, stdout, stderr = ssh_client.exec_command(f"ls -l {remote_path}")
        file_check = stdout.read().decode().strip()
        if "No such file" in file_check or not file_check:
            return {"status": "error", "message": "文件上传失败"}

        # 5. 🔥 注入回连 IP (关键修复：优先使用环境变量)
        # 读取 .env 中的 C2_HOST，如果存在则强制使用
        manual_c2_ip = os.getenv("C2_HOST", "")

        if manual_c2_ip:
            local_ip = manual_c2_ip
            print(f"[DEBUG] 使用配置文件的强制 C2 IP: {local_ip}")
        else:
            local_ip = _detect_local_ip_for_kali()
            print(f"[DEBUG] 自动检测到的 C2 回连 IP: {local_ip}")

        # 使用 sed 修改 Python 脚本中的 IP
        ssh_client.exec_command(f"sed -i 's/^FIXED_C2_IP = .*/FIXED_C2_IP = \"{local_ip}\"/g' {remote_path}")

        # 同时确保端口也是对的 (防止脚本里写死成其他端口)
        c2_port = "8001"
        ssh_client.exec_command(f"sed -i 's/^PORT = .*/PORT = \"{c2_port}\"/g' {remote_path}")

        # 6. 启动进程
        print(f"[DEBUG] 正在重启 Agent 进程...")
        ssh_client.exec_command("pkill -f wifi_scanner.py")
        time.sleep(1)

        cmd = f"nohup python3 {remote_path} > /tmp/agent.log 2>&1 &"
        ssh_client.exec_command(cmd)
        time.sleep(2)

        # 7. 检查存活
        stdin, stdout, stderr = ssh_client.exec_command("ps aux | grep wifi_scanner.py | grep -v grep")
        proc_info = stdout.read().decode().strip()

        if not proc_info:
            stdin, stdout, stderr = ssh_client.exec_command("cat /tmp/agent.log")
            log_content = stdout.read().decode().strip()
            return {"status": "error", "message": f"启动失败: {log_content[-100:]}"}

        print(f"[DEBUG] ✅ Agent 进程运行中 (PID: {proc_info.split()[1]})")

        # 8. 等待上线
        online_deadline = time.time() + 10
        print(f"[DEBUG] 等待 Agent 回连 ({local_ip}:8001)...")
        while time.time() < online_deadline:
            if (time.time() - c2_state.get("last_heartbeat", 0)) < 10 and c2_state.get("interfaces"):
                return {"status": "success", "message": "Agent 已成功部署并上线", "c2_ip": local_ip}
            await asyncio.sleep(1)

        # 超时未回连
        stdin, stdout, stderr = ssh_client.exec_command("tail -n 80 /tmp/agent.log || true")
        log_tail = stdout.read().decode(errors="ignore")
        return {
            "status": "warning",
            "message": f"Agent 已运行但未回连 (IP: {local_ip})，请检查防火墙或 .env 配置。",
            "c2_ip": local_ip,
            "agent_log_tail": log_tail
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ==========================================
# 4. 任务控制接口
# ==========================================

@router.get("/interfaces")
async def get_interfaces():
    """获取 Kali 网卡列表"""
    is_online = (time.time() - c2_state['last_heartbeat']) < 15
    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "等待 Agent 连接...", "mode": "-"}]}
    return {"interfaces": c2_state['interfaces']}


class ScanReq(BaseModel):
    interface: str = "wlan0"


@router.post("/scan/start")
async def trigger_scan(req: ScanReq, db: Session = Depends(get_session)):
    """[扫描] 清空数据库 -> 下发任务 -> 等待完成"""
    print(f"[*] [SCAN] 收到扫描请求，正在初始化数据库...")

    # 1. 清空旧数据
    db.exec(delete(TargetedClient))
    db.exec(delete(WiFiNetwork))
    db.commit()

    # 2. 下发任务
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        # 等待 Agent 回传 (25s 超时)
        await asyncio.wait_for(scan_complete_event.wait(), timeout=25.0)

        # 返回数量
        count = db.exec(select(WiFiNetwork)).all()
        return {"status": "success", "count": len(count)}
    except asyncio.TimeoutError:
        c2_state['current_task'] = 'idle'
        return {"status": "timeout", "message": "扫描超时，Agent 未响应"}


@router.post("/scan/stop")
async def stop_scan():
    """停止扫描 (C2模式下只需将任务置空)"""
    c2_state['current_task'] = 'idle'
    return {"status": "stopped"}


# === 🔥 关键兼容接口：为 Evil Twin 提供扫描结果 ===
@router.get("/scan/results")
async def get_scan_results(db: Session = Depends(get_session)):
    """
    [适配 Evil Twin] 从数据库读取扫描结果
    返回格式适配 Evil Twin 下拉框: [{bssid, channel, ssid, label}, ...]
    """
    networks = db.exec(select(WiFiNetwork).order_by(WiFiNetwork.signal_dbm.desc())).all()

    data = []
    for net in networks:
        data.append({
            "bssid": net.bssid,
            "channel": str(net.channel),
            "ssid": net.ssid,
            "power": str(net.signal_dbm),
            "label": f"[{net.channel}] {net.ssid} ({net.signal_dbm}dBm)"
        })
    return {"status": "success", "data": data}


# 原有的 /networks 接口保留给普通页面使用
@router.get("/networks")
async def get_networks_db(db: Session = Depends(get_session)):
    return db.exec(select(WiFiNetwork).order_by(WiFiNetwork.signal_dbm.desc())).all()


class MonitorReq(BaseModel):
    bssid: str
    channel: int
    interface: str = "wlan0"


@router.post("/monitor/start")
async def start_monitor(req: MonitorReq, db: Session = Depends(get_session)):
    is_online = (time.time() - c2_state['last_heartbeat']) < 15
    if not is_online:
        return {"status": "error", "message": "Agent 离线，无法下发监听任务"}

    bssid = (req.bssid or "").strip().upper()
    print(f"[*] [MONITOR] 锁定目标: {bssid} (CH: {req.channel})")

    # 清除旧的客户端数据
    db.exec(delete(TargetedClient).where(TargetedClient.network_bssid == bssid))
    db.commit()

    monitor_state["last_update"] = 0.0
    monitor_state["last_count"] = 0
    monitor_state["target_bssid"] = bssid

    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = {**req.dict(), "bssid": bssid}
    return {"status": "queued"}


@router.post("/monitor/stop")
async def stop_monitor():
    c2_state['current_task'] = 'idle'
    return {"status": "stopped"}


@router.get("/monitor/clients/{bssid}")
async def get_monitored_clients(bssid: str, db: Session = Depends(get_session)):
    key = (bssid or "").strip().upper()
    return db.exec(select(TargetedClient).where(TargetedClient.network_bssid == key)).all()


# ==========================================
# 5. Agent 回调接口 (C2核心)
# ==========================================

class AgentRegister(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(data: AgentRegister):
    """Agent 启动时注册网卡信息"""
    c2_state['interfaces'] = data.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "ok"}


@router.get("/agent/heartbeat")
async def agent_heartbeat():
    """Agent 轮询任务"""
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
    """接收 Agent 回传的数据"""

    # A. 扫描结果 (批量入库)
    if payload.type == 'scan_result' and payload.networks:
        print(f"[*] [CALLBACK] 收到 {len(payload.networks)} 个 AP 数据")
        for net in payload.networks:
            # Upsert
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
        scan_complete_event.set()  # 通知前端扫描完成
        c2_state['current_task'] = 'idle'
        return {"status": "persisted"}

    # B. 监听结果 (实时更新客户端)
    if payload.type == 'monitor_update' and payload.data:
        target = (c2_state.get('task_params') or {}).get('bssid') or ""
        target = str(target).strip().upper()

        monitor_state["last_update"] = time.time()
        monitor_state["last_count"] = len(payload.data)

        for item in payload.data:
            mac = item.get('mac') or item.get('client_mac')
            if not mac: continue
            mac = str(mac).strip().upper()

            client = db.exec(select(TargetedClient).where(
                TargetedClient.client_mac == mac,
                TargetedClient.network_bssid == target
            )).first()

            pkt = _safe_int(item.get('packets'), 0)
            sig = _safe_int(item.get('signal'), -100)

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
        db.commit()
        return {"status": "updated"}

    return {"status": "ok"}