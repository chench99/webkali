from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
from app.core.ssh_manager import ssh_client
import time
import os

router = APIRouter()

class HandshakeRequest(BaseModel):
    ssid: str
    bssid: str
    channel: int
    interface: str = "wlan0"
    timeout: int = 90

class EvilTwinRequest(BaseModel):
    ssid: str
    interface: str = "wlan0"

@router.post("/handshake/start")
async def start_handshake_capture(req: HandshakeRequest):
    print(f"\n[DEBUG] ========== 启动握手包捕获 ==========")
    
    # 1. 连接 SSH
    if not ssh_client.client:
        ssh_client.connect()
        if not ssh_client.client:
            return {"status": "error", "message": "SSH 连接失败"}

    # 2. 部署脚本 (自动寻址)
    current_file = Path(__file__).resolve()
    # 向上寻找 kali_payloads 目录
    # 假设当前文件在 backend/app/api/v1/endpoints/attack.py
    # 需要向上找 5 层到达项目根目录，或者寻找包含 kali_payloads 的父级目录
    project_root = None
    for p in current_file.parents:
        if (p / "kali_payloads").exists():
            project_root = p
            break
            
    if not project_root:
        # 开发环境容错：如果在 backend 目录下运行
        if Path("kali_payloads").exists():
             project_root = Path(".")
        else:
             return {"status": "error", "message": "找不到 kali_payloads 目录"}

    payload_src = project_root / "kali_payloads" / "handshake_worker.py"
    remote_script = "/tmp/handshake_worker.py"

    if not payload_src.exists():
        return {"status": "error", "message": f"本地脚本缺失: {payload_src}"}

    try:
        print(f"[DEBUG] 上传脚本: {payload_src}")
        ssh_client.upload_payload(str(payload_src), "handshake_worker.py")
        
        # 3. 执行脚本 (重要：设置 timeout 比脚本运行时间稍长)
        # 脚本参数: BSSID Channel Timeout Interface
        cmd = f"python3 {remote_script} {req.bssid} {req.channel} {req.timeout} {req.interface}"
        print(f"[DEBUG] 执行 Kali 命令: {cmd}")
        
        # 【关键修复】读取输出流会阻塞当前线程，直到脚本结束
        # 这确保了后端会等待 Kali 跑完那 45 秒
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=req.timeout + 10)
        
        # 读取日志
        output = stdout.read().decode()
        error = stderr.read().decode()
        
        print(f"[DEBUG] Kali 输出:\n{output}")
        
        if "[SUCCESS] CAPTURED" in output:
            # 下载文件逻辑
            remote_cap = "/tmp/handshake_capture-01.cap"
            save_dir = project_root / "backend" / "captures"
            
            # 确保存储目录存在
            if not save_dir.exists():
                save_dir.mkdir(parents=True)
            
            clean_ssid = "".join(x for x in req.ssid if x.isalnum())
            local_filename = f"{clean_ssid}_{req.bssid.replace(':','')}.cap"
            local_path = save_dir / local_filename
            
            print(f"[DEBUG] 下载文件: {remote_cap} -> {local_path}")
            sftp = ssh_client.client.open_sftp()
            sftp.get(remote_cap, str(local_path))
            sftp.close()
            
            return {
                "status": "success", 
                "message": "握手包捕获成功", 
                "file": local_filename,
                "logs": output[-500:] # 只返回最后500字符日志
            }
        else:
            return {
                "status": "fail", 
                "message": "超时未捕获", 
                "logs": output[-500:] if output else error
            }

    except Exception as e:
        print(f"[DEBUG] ❌ 异常: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.post("/eviltwin/start")
async def start_eviltwin(req: EvilTwinRequest):
    print(f"[DEBUG] 启动 Evil Twin: {req.ssid}")
    # 这里需要实现真实的 Evil Twin 逻辑，目前先返回模拟成功
    return {"status": "success", "message": "Evil Twin 部署指令已下发"}