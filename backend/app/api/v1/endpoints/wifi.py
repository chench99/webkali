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
import socket
from datetime import datetime
from pathlib import Path

router = APIRouter()

# --- C2 状态机 ---
c2_state = {
    "interfaces": [],
    "current_task": "idle",
    "task_params": {},
    "last_heartbeat": 0,
    "networks": []
}

scan_complete_event = asyncio.Event()


# ==========================================
# 1. 智能部署接口 (路径修复版)
# ==========================================
@router.post("/agent/deploy")
async def deploy_agent_via_ssh():
    """
    [C2] 强制重装 Agent 并执行健康检查
    """
    print(f"\n[DEBUG] ========== 开始部署 Agent ==========")

    # 1. 连接 SSH
    if not ssh_client.client:
        print(f"[DEBUG] 正在建立 SSH 连接...")
        ssh_client.connect()
        if not ssh_client.client:
            print(f"[DEBUG] ❌ SSH 连接失败")
            return {"status": "error", "message": "SSH 连接失败，请检查 .env 配置"}

    # 2. 智能定位 Payload (修复路径查找逻辑)
    current_file = Path(__file__).resolve()
    # /backend/app/api/v1/endpoints/wifi.py
    # parents[0]=endpoints, [1]=v1, [2]=api, [3]=app, [4]=backend, [5]=项目根目录

    possible_paths = [
        # 优先级1: 标准结构 (项目根目录/kali_payloads) -> 对应 parents[5]
        current_file.parents[5] / "kali_payloads" / "wifi_scanner.py",

        # 优先级2: 放在 backend 下 (backend/kali_payloads) -> 对应 parents[4]
        current_file.parents[4] / "kali_payloads" / "wifi_scanner.py",

        # 优先级3: 相对运行路径
        Path("kali_payloads/wifi_scanner.py").resolve(),
        Path("../kali_payloads/wifi_scanner.py").resolve()
    ]

    payload_src = None
    for p in possible_paths:
        if p.exists():
            payload_src = p
            print(f"[DEBUG] ✅ 成功定位 Payload: {p}")
            break

    if not payload_src:
        # 打印调试信息帮助排查
        print(f"[DEBUG] ❌ 无法找到 wifi_scanner.py，已尝试路径:")
        for p in possible_paths:
            print(f"   - {p}")
        return {"status": "error", "message": "服务端找不到 wifi_scanner.py，请检查文件位置"}

    try:
        # 3. 上传文件
        remote_path = "/tmp/wifi_scanner.py"
        print(f"[DEBUG] 正在上传至 Kali: {remote_path}")
        ssh_client.upload_payload(str(payload_src), "wifi_scanner.py")

        # 4. [校验] 检查文件是否存在
        stdin, stdout, stderr = ssh_client.exec_command(f"ls -l {remote_path}")
        file_check = stdout.read().decode().strip()
        if "No such file" in file_check or not file_check:
            print(f"[DEBUG] ❌ 上传校验失败: 文件不存在")
            return {"status": "error", "message": "文件上传失败 (SFTP Error)"}
        print(f"[DEBUG] ✅ 文件校验通过: {file_check.split(' ')[-1]}")

        # 5. [注入] 获取本机 IP 并写入脚本
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 连接公网 IP (不需要真实连通) 来获取准确的内网 IP
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except:
            local_ip = "127.0.0.1"
        finally:
            s.close()

        print(f"[DEBUG] 注入 C2 IP: {local_ip}")
        # 使用 sed 替换脚本中的空 IP 配置
        ssh_client.exec_command(f"sed -i 's/FIXED_C2_IP = \"\"/FIXED_C2_IP = \"{local_ip}\"/g' {remote_path}")

        # 6. [启动] 杀进程 -> 启动 -> 检查
        print(f"[DEBUG] 重启进程...")
        ssh_client.exec_command("pkill -f wifi_scanner.py")
        time.sleep(1)

        # 启动命令：输出重定向很重要，防止 SSH 阻塞
        cmd = f"nohup python3 {remote_path} > /tmp/agent.log 2>&1 &"
        ssh_client.exec_command(cmd)

        # 等待进程初始化
        time.sleep(2)

        # 7. [校验] 检查进程是否存活
        stdin, stdout, stderr = ssh_client.exec_command("ps aux | grep wifi_scanner.py | grep -v grep")
        proc_info = stdout.read().decode().strip()

        if not proc_info:
            # 读取错误日志
            stdin, stdout, stderr = ssh_client.exec_command("cat /tmp/agent.log")
            log_content = stdout.read().decode().strip()
            print(f"[DEBUG] ❌ 进程启动失败! 日志:\n{log_content}")
            return {"status": "error", "message": f"Agent 启动失败，Kali 报错: {log_content[-100:]}"}

        print(f"[DEBUG] ✅ Agent 运行中: {proc_info}")
        print(f"[DEBUG] ========== 部署完成 ==========\n")

        return {"status": "success", "message": "Agent 已成功部署并上线"}

    except Exception as e:
        print(f"[DEBUG] ❌ 异常: {str(e)}")
        return {"status": "error", "message": str(e)}


# ==========================================
# 2. 任务控制与数据交互
# ==========================================

@router.get("/interfaces")
async def get_interfaces():
    # 15秒无心跳视为离线
    is_online = (time.time() - c2_state['last_heartbeat']) < 15
    if not c2_state['interfaces'] or not is_online:
        return {"interfaces": [{"name": "waiting", "display": "等待 Agent 连接...", "mode": "-"}]}
    return {"interfaces": c2_state['interfaces']}


class ScanReq(BaseModel):
    interface: str = "wlan0"


@router.post("/scan/start")
async def trigger_scan(req: ScanReq):
    print(f"[DEBUG] 收到扫描请求: {req.interface}")
    scan_complete_event.clear()
    c2_state['current_task'] = 'scan'
    c2_state['task_params'] = {'interface': req.interface}
    c2_state['networks'] = []

    try:
        # 等待 Agent 回传 (25s 超时)
        await asyncio.wait_for(scan_complete_event.wait(), timeout=25.0)
        return {"status": "success", "networks": c2_state['networks']}
    except asyncio.TimeoutError:
        c2_state['current_task'] = 'idle'
        return {"status": "timeout", "message": "扫描超时，Agent 未响应"}


class MonitorReq(BaseModel):
    bssid: str
    channel: int
    interface: str = "wlan0"


@router.post("/monitor/start")
async def start_monitor(req: MonitorReq):
    print(f"[DEBUG] 启动监听: {req.bssid} @ CH {req.channel}")
    c2_state['current_task'] = 'monitor_target'
    c2_state['task_params'] = req.dict()
    return {"status": "queued"}


@router.post("/monitor/stop")
async def stop_monitor():
    c2_state['current_task'] = 'idle'
    return {"status": "stopped"}


@router.get("/monitor/clients/{bssid}")
async def get_monitored_clients(bssid: str, db: Session = Depends(get_session)):
    return db.exec(select(TargetedClient).where(TargetedClient.network_bssid == bssid)).all()


# ==========================================
# 3. Agent 回调逻辑
# ==========================================

class AgentRegister(BaseModel):
    interfaces: List[Dict]


@router.post("/register_agent")
async def register_agent(data: AgentRegister):
    # print(f"[DEBUG] Agent 心跳: {len(data.interfaces)} 个网卡")
    c2_state['interfaces'] = data.interfaces
    c2_state['last_heartbeat'] = time.time()
    return {"status": "ok"}


@router.get("/agent/heartbeat")
async def agent_heartbeat():
    c2_state['last_heartbeat'] = time.time()
    if c2_state['current_task'] != 'idle':
        return {
            "status": "ok",
            "task": c2_state['current_task'],
            "params": c2_state['task_params']
        }
    return {"status": "ok", "task": "idle"}


class CallbackData(BaseModel):
    type: str
    networks: Optional[List[Dict]] = None
    data: Optional[List[Dict]] = None


@router.post("/callback")
async def agent_callback(payload: CallbackData, db: Session = Depends(get_session)):
    # 1. 处理扫描结果
    if payload.type == 'scan_result' and payload.networks is not None:
        print(f"[DEBUG] 收到扫描结果: {len(payload.networks)} APs")
        c2_state['networks'] = payload.networks
        c2_state['current_task'] = 'idle'
        scan_complete_event.set()
        return {"status": "received"}

    # 2. 处理监听更新
    if payload.type == 'monitor_update' and payload.data:
        target = c2_state['task_params'].get('bssid')
        if not target: return {"status": "ignored"}

        # print(f"[DEBUG] 更新客户端数据: {len(payload.data)} 个")
        for item in payload.data:
            mac = item.get('mac')
            if not mac: continue

            # 使用 Upsert (存在则更新，不存在则插入)
            client = db.exec(select(TargetedClient).where(
                TargetedClient.client_mac == mac,
                TargetedClient.network_bssid == target
            )).first()

            if not client:
                client = TargetedClient(
                    network_bssid=target,
                    client_mac=mac,
                    packet_count=item.get('packets', 0),
                    signal=item.get('signal', -100),
                    last_seen=datetime.utcnow()
                )
                db.add(client)
            else:
                client.packet_count = item.get('packets', 0)
                client.signal = item.get('signal', -100)
                client.last_seen = datetime.utcnow()
                db.add(client)

        db.commit()
        return {"status": "updated"}

    return {"status": "ok"}