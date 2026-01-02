import json
import asyncio
from app.core.ssh_manager import ssh_client
from app.core.database import get_session
from app.models.wifi import WiFiNetwork
from sqlmodel import select


class WifiScanner:
    async def start(self):
        # 1. 上传脚本
        remote_path = ssh_client.upload_payload("kali_payloads/wifi_scanner.py", "wifi_scanner.py")

        # 2. 远程执行
        # 注意：这里我们只启动，不一直等待，或者用流式读取
        cmd = f"python3 {remote_path} scan"
        stdin, stdout, stderr = ssh_client.exec_command(cmd)

        # 3. 实时读取输出 (这里为了简单演示，只读一次，实际应该用 WebSocket)
        # 在生产环境中，你会用一个后台任务循环读取 stdout
        for line in stdout:
            try:
                data = json.loads(line)
                if "networks" in data:
                    self.save_to_db(data["networks"])
            except:
                pass

    def save_to_db(self, networks):
        # 简单的入库逻辑
        # 实际代码需要处理 Session
        print(f"[*] 扫描到 {len(networks)} 个 WiFi")
        # 这里补全数据库写入代码...


scanner = WifiScanner()