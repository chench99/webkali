import os
import asyncio
import subprocess

# ==============================
# 👇 修改这里：使用你提供的真实路径
# 注意：前面加 r 是为了防止反斜杠转义报错
HASHCAT_EXE = r"D:\hashcat-7.1.2\hashcat.exe"


# ==============================

class HashcatEngine:
    async def crack_handshake(self, handshake_path: str, wordlist_path: str):
        # 检查文件是否存在
        if not os.path.exists(HASHCAT_EXE):
            print(f"[!] 错误: 找不到 Hashcat，请检查路径: {HASHCAT_EXE}")
            return {"error": "Hashcat executable not found"}

        # ... (下面的代码保持不变)

        # 构造命令
        # -m 22000: WPA-PBKDF2-PMKID+EAPOL
        # -w 3: High Workload (高负载)
        cmd = [
            HASHCAT_EXE,
            "-m", "22000",
            "-a", "0",
            "-w", "3",
            handshake_path,
            wordlist_path,
            "--status", "--status-timer", "1"
        ]

        print(f"[*] Starting GPU Crack: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # 这里简化处理，直接返回进程对象，实际应该用 WebSocket 推送进度
        return process


# 单例
cracker = HashcatEngine()