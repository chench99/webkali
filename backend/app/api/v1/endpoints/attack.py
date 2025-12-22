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
    timeout: int = 90  # 默认 90秒

class EvilTwinRequest(BaseModel):
    ssid: str
    interface: str = "wlan0"

@router.post("/handshake/start")
async def start_handshake_capture(req: HandshakeRequest):
    print(f"\n[DEBUG] ========== 启动握手包捕获 ==========")
    
    if not ssh_client.client:
        ssh_client.connect()
        if not ssh_client.client:
            return {"status": "error", "message": "SSH 连接失败"}

    # 自动寻址 payload
    current_file = Path(__file__).resolve()
    project_root = None
    for p in current_file.parents:
        if (p / "kali_payloads").exists():
            project_root = p
            break
            
    if not project_root:
        if Path("kali_payloads").exists(): project_root = Path(".")
        else: return {"status": "error", "message": "找不到 kali_payloads 目录"}

    payload_src = project_root / "kali_payloads" / "handshake_worker.py"
    remote_script = "/tmp/handshake_worker.py"

    if not payload_src.exists():
        return {"status": "error", "message": f"本地脚本缺失: {payload_src}"}

    try:
        print(f"[DEBUG] 上传脚本: {payload_src}")
        ssh_client.upload_payload(str(payload_src), "handshake_worker.py")
        
        # 执行脚本
        cmd = f"python3 {remote_script} {req.bssid} {req.channel} {req.timeout} {req.interface}"
        print(f"[DEBUG] 执行 Kali 命令: {cmd}")
        
        # 阻塞等待执行结果
        stdin, stdout, stderr = ssh_client.exec_command(cmd, timeout=req.timeout + 10)
        output = stdout.read().decode()
        error = stderr.read().decode()
        print(f"[DEBUG] Kali 输出:\n{output}")
        
        if "[SUCCESS] CAPTURED" in output:
            save_dir = project_root / "backend" / "captures"
            if not save_dir.exists(): save_dir.mkdir(parents=True)
            
            clean_ssid = "".join(x for x in req.ssid if x.isalnum())
            base_filename = f"{clean_ssid}_{req.bssid.replace(':','')}"
            
            # 1. 下载 .cap 文件
            remote_cap = "/tmp/handshake_capture-01.cap"
            local_cap = f"{base_filename}.cap"
            local_cap_path = save_dir / local_cap
            
            sftp = ssh_client.client.open_sftp()
            sftp.get(remote_cap, str(local_cap_path))
            print(f"[DEBUG] CAP 下载成功: {local_cap}")
            
            # 2. [新增] 检查并下载 .hc22000 文件
            local_hc = None
            if "[SUCCESS] CONVERTED" in output:
                remote_hc = "/tmp/handshake_capture-01.hc22000"
                local_hc = f"{base_filename}.hc22000"
                local_hc_path = save_dir / local_hc
                try:
                    sftp.get(remote_hc, str(local_hc_path))
                    print(f"[DEBUG] HC22000 下载成功: {local_hc}")
                except Exception as e:
                    print(f"[DEBUG] HC22000 下载失败: {e}")
                    local_hc = None
            
            sftp.close()
            
            return {
                "status": "success", 
                "message": "握手包捕获成功", 
                "file_cap": local_cap,
                "file_hc": local_hc,  # 返回 HC 文件名
                "logs": output[-500:]
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
    return {"status": "success", "message": "Evil Twin 部署指令已下发"}