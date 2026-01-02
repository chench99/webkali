from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
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

router = APIRouter()

# --- C2 状态机 ---
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
_handshake_dir = Path(__file__).resolve().parents[5] / "captures" / "handshakes"
_handshake_dir.mkdir(parents=True, exist_ok=True)


def _normalize_bssid(value: str) -> str:
    if not value:
        return "unknown"
    v = value.strip().lower()
    if re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", v):
        return v
    return "unknown"

def _detect_local_ip_for_kali() -> str:
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
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        if not s:
            return default
        return int(float(s))
    except Exception:
        return default


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
    if lines < 1:
        lines = 1
    if lines > 500:
        lines = 500
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


@router.post("/handshake/upload")
async def upload_handshake(file: UploadFile = File(...), bssid: str = Form(""), ssid: str = Form("")):
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    ext = Path(filename).suffix.lower()
    if ext not in [".cap", ".pcap", ".pcapng"]:
        raise HTTPException(status_code=400, detail="仅支持 .cap/.pcap/.pcapng")

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
    for p in sorted(_handshake_dir.glob("handshake_*"), key=lambda x: x.stat().st_mtime, reverse=True):
        name = p.name
        if bssid_norm and (f"handshake_{bssid_norm.replace(':', '')}_" not in name):
            continue
        st = p.stat()
        items.append(
            {
                "filename": name,
                "size": st.st_size,
                "mtime": int(st.st_mtime)
            }
        )
    return {"items": items}


@router.get("/handshake/download/{filename}")
async def download_handshake(filename: str):
    name = Path(filename).name
    path = _handshake_dir / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(path), filename=name)


# ==========================================
# 1. 智能部署接口 (带详细调试日志)
# ==========================================
@router.post("/agent/deploy")
async def deploy_agent_via_ssh():
    """
    [C2] 强制重装 Agent 并执行双重健康检查
    """
    print(f"\n[DEBUG] ========== 开始部署 Agent ==========")

    # 1. SSH 连接检查
    if not ssh_client.client:
        print(f"[DEBUG] 正在建立 SSH 连接...")
        ssh_client.connect()
        if not ssh_client.client:
            print(f"[DEBUG] ❌ SSH 连接失败，请检查 .env 配置")
            return {"status": "error", "message": "SSH 连接失败"}
    print(f"[DEBUG] ✅ SSH 连接状态正常")

    # 2. 智能定位 Payload (递归向上查找)
    current_file = Path(__file__).resolve()
    # 尝试多种可能的路径结构
    possible_paths = [
        current_file.parents[5] / "kali_payloads" / "wifi_scanner.py",  # 标准生产环境
        current_file.parents[4] / "kali_payloads" / "wifi_scanner.py",  # 开发环境
        Path("kali_payloads/wifi_scanner.py").resolve(),  # 相对路径
        Path("../kali_payloads/wifi_scanner.py").resolve()
    ]

    payload_src = None
    for p in possible_paths:
        if p.exists():
            payload_src = p
            print(f"[DEBUG] ✅ 成功定位 Payload 文件: {p}")
            break

    if not payload_src:
        print(f"[DEBUG] ❌ 严重错误: 无法在服务端找到 wifi_scanner.py")
        return {"status": "error", "message": "服务端文件缺失"}

    try:
        remote_path = "/tmp/wifi_scanner.py"

        # 3. 上传文件
        print(f"[DEBUG] 正在上传至 Kali: {remote_path}")
        ssh_client.upload_payload(str(payload_src), "wifi_scanner.py")

        # 4. [验尸逻辑 1] 检查文件是否存在
        stdin, stdout, stderr = ssh_client.exec_command(f"ls -l {remote_path}")
        file_check = stdout.read().decode().strip()
        if "No such file" in file_check or not file_check:
            print(f"[DEBUG] ❌ 上传验证失败: 文件不存在")
            return {"status": "error", "message": "文件上传失败"}
        print(f"[DEBUG] ✅ 文件上传验证通过: {file_check.split(' ')[-1]}")

        # 5. 注入 IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except:
            local_ip = "127.0.0.1"
        finally:
            s.close()

        local_ip = _detect_local_ip_for_kali()
        print(f"[DEBUG] 注入 C2 回连 IP: {local_ip}")
        ssh_client.exec_command(f"sed -i 's/^FIXED_C2_IP = .*/FIXED_C2_IP = \"{local_ip}\"/g' {remote_path}")

        # 6. 启动进程
        print(f"[DEBUG] 正在重启 Agent 进程...")
        ssh_client.exec_command("pkill -f wifi_scanner.py")
        time.sleep(1)

        cmd = f"nohup python3 {remote_path} > /tmp/agent.log 2>&1 &"
        ssh_client.exec_command(cmd)

        # 等待进程初始化
        time.sleep(2)

        # 7. [验尸逻辑 2] 检查进程是否存活
        stdin, stdout, stderr = ssh_client.exec_command("ps aux | grep wifi_scanner.py | grep -v grep")
        proc_info = stdout.read().decode().strip()

        if not proc_info:
            stdin, stdout, stderr = ssh_client.exec_command("cat /tmp/agent.log")
            log_content = stdout.read().decode().strip()
            print(f"[DEBUG] ❌ 进程启动失败! Kali 日志:\n{log_content}")
            return {"status": "error", "message": f"启动失败: {log_content[-100:]}"}

        print(f"[DEBUG] ✅ Agent 进程运行中 (PID: {proc_info.split()[1]})")
        print(f"[DEBUG] ========== 部署流程结束 ==========\n")
        online_deadline = time.time() + 12
        while time.time() < online_deadline:
            if (time.time() - c2_state.get("last_heartbeat", 0)) < 10 and c2_state.get("interfaces"):
                return {"status": "success", "message": "Agent 已成功部署并上线", "c2_ip": local_ip}
            await asyncio.sleep(1)

        stdin, stdout, stderr = ssh_client.exec_command("tail -n 80 /tmp/agent.log || true")
        log_tail = stdout.read().decode(errors="ignore")
        return {
            "status": "success",
            "message": "Agent 已部署并运行，但尚未回连（仍显示离线属正常现象）",
            "c2_ip": local_ip,
            "hint": "常见原因：回连 IP 不可达 / Windows 防火墙拦截 8001 / Kali 到 Windows 网络不通",
            "agent_log_tail": log_tail
        }

    except Exception as e:
        print(f"[DEBUG] ❌ 部署异常: {str(e)}")
        return {"status": "error", "message": str(e)}


# ==========================================
# 2. 任务控制与数据交互
# ==========================================

@router.get("/interfaces")
async def get_interfaces():
    is_online = (time.time() - c2_state['last_heartbeat']) < 15
    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "等待 Agent 连接...", "mode": "-"}]}
    return {"interfaces": c2_state['interfaces']}


class ScanReq(BaseModel):
    interface: str = "wlan0"


@router.post("/scan/start")
async def trigger_scan(req: ScanReq, db: Session = Depends(get_session)):
    """
    [扫描] 清空数据库 -> 下发任务 -> 等待完成
    """
    print(f"[*] [SCAN] 收到扫描请求，正在初始化数据库...")

    # 1. 立即清空旧数据 (持久化模式核心)
    # 注意：删除顺序很重要，先删子表(TargetedClient)，再删主表(WiFiNetwork)
    db.exec(delete(TargetedClient))
    db.exec(delete(WiFiNetwork))
    db.commit()
    print(f"[*] [SCAN] 数据库已重置")

    # 2. 下发任务
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}

    try:
        # 等待 Agent 回传 (25s 超时)
        await asyncio.wait_for(scan_complete_event.wait(), timeout=25.0)

        # 3. 从数据库读取结果返回
        count = db.exec(select(WiFiNetwork)).all()
        return {"status": "success", "count": len(count)}
    except asyncio.TimeoutError:
        c2_state['current_task'] = 'idle'
        return {"status": "timeout", "message": "扫描超时，Agent 未响应"}


@router.get("/networks")
async def get_networks_db(db: Session = Depends(get_session)):
    """从数据库获取 WiFi 列表"""
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

@router.post("/attack/deauth")
async def request_deauth_attack(bssid: str, interface: str = "wlan0", duration: int = 60):
    return {
        "status": "disabled",
        "message": "该能力默认未启用。仅在获得明确授权与合规配置后才可开启。",
        "params": {"bssid": bssid, "interface": interface, "duration": duration}
    }


@router.get("/monitor/clients/{bssid}")
async def get_monitored_clients(bssid: str, db: Session = Depends(get_session)):
    """从数据库获取指定 AP 的客户端"""
    key = (bssid or "").strip().upper()
    return db.exec(select(TargetedClient).where(TargetedClient.network_bssid == key)).all()


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
            # Upsert 逻辑
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
        scan_complete_event.set()  # 解锁等待
        c2_state['current_task'] = 'idle'
        return {"status": "persisted"}

    # === B. 处理监听客户端 (实时入库) ===
    if payload.type == 'monitor_update' and payload.data:
        target = (c2_state.get('task_params') or {}).get('bssid') or ""
        target = str(target).strip().upper()
        if not target:
            return {"status": "ignored"}

        monitor_state["last_update"] = time.time()
        monitor_state["last_count"] = len(payload.data)
        monitor_state["target_bssid"] = target

        for item in payload.data:
            mac = item.get('mac') or item.get('client_mac')
            if not mac:
                continue
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
