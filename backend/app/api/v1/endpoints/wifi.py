from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select, delete
from app.core.database import get_session
from app.models.wifi import WiFiNetwork, TargetedClient
from app.core.ssh_manager import ssh_client
from pydantic import BaseModel
from typing import List, Dict, Optional
import time
import os
import asyncio
import socket
from datetime import datetime
from pathlib import Path

router = APIRouter()

# --- C2 状态机 ---
c2_state = {
    "interfaces": [],
    "current_task": "idle",
    "task_params": {},
    "last_heartbeat": 0
}

scan_complete_event = asyncio.Event()


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

        print(f"[DEBUG] 注入 C2 回连 IP: {local_ip}")
        ssh_client.exec_command(f"sed -i 's/FIXED_C2_IP = \"\"/FIXED_C2_IP = \"{local_ip}\"/g' {remote_path}")

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

        return {"status": "success", "message": "Agent 已成功部署并上线"}

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
    db.exec(delete(WiFiNetwork))
    db.exec(delete(TargetedClient))
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
async def start_monitor(req: MonitorReq):
    print(f"[*] [MONITOR] 锁定目标: {req.bssid} (CH: {req.channel})")
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = req.dict()
    return {"status": "queued"}


@router.post("/monitor/stop")
async def stop_monitor():
    c2_state['current_task'] = 'idle'
    return {"status": "stopped"}


@router.get("/monitor/clients/{bssid}")
async def get_monitored_clients(bssid: str, db: Session = Depends(get_session)):
    """从数据库获取指定 AP 的客户端"""
    return db.exec(select(TargetedClient).where(TargetedClient.network_bssid == bssid)).all()


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
        target = c2_state['task_params'].get('bssid')
        if not target: return {"status": "ignored"}

        for item in payload.data:
            mac = item.get('mac')
            if not mac: continue

            client = db.exec(select(TargetedClient).where(
                TargetedClient.client_mac == mac,
                TargetedClient.network_bssid == target
            )).first()

            pkt = int(item.get('packets', 0))
            sig = int(item.get('signal', -100))

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