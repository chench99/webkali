from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.modules.ai_agent.service import ai_service
from app.core.ssh_manager import ssh_client
import os

router = APIRouter()


# === 请求体模型 ===
class AIAnalysisRequest(BaseModel):
    ssid: str
    encryption: str
    bssid: str


class EvilTwinRequest(BaseModel):
    ssid: str
    interface: str = "wlan0"


# === 辅助函数：获取脚本绝对路径 ===
def get_payload_path(filename: str):
    """
    智能获取 Windows 本地脚本的绝对路径
    解决 "FileNotFound" 问题
    """
    # 获取当前文件 (attack.py) 的目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 回退 5 层找到项目根目录
    project_root = os.path.abspath(os.path.join(current_dir, "../../../../.."))
    # 拼接 kali_payloads 路径
    payload_path = os.path.join(project_root, "kali_payloads", filename)

    if not os.path.exists(payload_path):
        print(f"[!] 错误: 找不到本地脚本 -> {payload_path}")
        return None
    return payload_path


# =======================
# 1. AI 战术分析接口
# =======================
@router.post("/ai/analyze_target")
async def analyze_target(req: AIAnalysisRequest):
    """
    调用 DeepSeek 分析目标 WiFi 的弱点和攻击向量
    """
    print(f"[*] 收到 AI 分析请求: {req.ssid} ({req.encryption})")

    # 模拟获取厂商 (可以通过 MAC 地址前3位查询，这里先简化)
    vendor = "Unknown"

    # 调用 AI 服务 (会去请求 DeepSeek API)
    result = ai_service.analyze_wifi_target(req.ssid, req.encryption, vendor)

    return result


# =======================
# 2. 钓鱼攻击接口 (Evil Twin)
# =======================
@router.post("/eviltwin/start")
async def start_evil_twin(req: EvilTwinRequest):
    """
    启动双子热点钓鱼攻击
    """
    # 1. 确保 SSH 连接
    if not ssh_client.client:
        ssh_client.connect()

    # 2. 获取本地脚本路径
    local_script = get_payload_path("fake_ap.py")
    if not local_script:
        return {"status": "error", "msg": "Windows端找不到 fake_ap.py 脚本"}

    # 3. 上传脚本到 Kali
    print(f"[*] 正在上传钓鱼脚本: {local_script}")
    remote_path = ssh_client.upload_payload(local_script, "fake_ap.py")

    if not remote_path:
        return {"status": "error", "msg": "脚本上传失败"}

    # 4. 赋予执行权限
    ssh_client.exec_command(f"chmod +x {remote_path}")

    # 5. 执行脚本
    # 格式: python3 fake_ap.py "SSID" "INTERFACE"
    print(f"[*] 启动伪造热点: {req.ssid} on {req.interface}")
    cmd = f"nohup python3 {remote_path} '{req.ssid}' {req.interface} > /tmp/fake_ap.log 2>&1 &"
    ssh_client.exec_command(cmd)

    return {
        "status": "started",
        "msg": f"正在伪造热点: {req.ssid}",
        "log_path": "/tmp/fake_ap.log"
    }