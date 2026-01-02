import subprocess
import os
import sys
import threading
import signal
import shutil
import re
from pathlib import Path
from app.core.config import settings

class CrackEngine:
    def __init__(self):
        self.process = None
        self.is_running = False
        self.logs = []
        self.current_task = {}
        self.crack_status = {
            "state": "Idle",
            "progress": 0,
            "speed": "0 H/s",
            "eta": "-",
            "recovered": "0/0"
        }
        
        # 自动定位项目根目录
        self.backend_root = Path(__file__).resolve().parents[3]
        self.captures_dir = self.backend_root / "captures"
        self.wordlists_dir = self.backend_root / "wordlists"
        
        self.captures_dir.mkdir(exist_ok=True)
        self.wordlists_dir.mkdir(exist_ok=True)

    def get_files(self, file_type):
        target_dir = self.captures_dir if file_type == 'handshake' else self.wordlists_dir
        exts = ['.cap', '.pcap', '.hc22000'] if file_type == 'handshake' else ['.txt', '.dict']
        files = []
        if target_dir.exists():
            for f in target_dir.iterdir():
                if f.suffix in exts:
                    files.append(f.name)
        return sorted(files)

    def start_crack(self, handshake_file, wordlist_file):
        if self.is_running:
            return {"status": "error", "message": "任务运行中"}

        # === 1. 智能文件检查与自动切换 ===
        target_file = handshake_file
        
        # 如果用户选的是 .cap，我们去看看有没有同名的 .hc22000
        if handshake_file.endswith(".cap"):
            hc_file = handshake_file.replace(".cap", ".hc22000")
            if (self.captures_dir / hc_file).exists():
                self.logs = [f"[AUTO] 自动切换为 Hashcat 格式: {hc_file}"]
                target_file = hc_file
            else:
                # 【重要】如果没有 hc22000，直接报错
                err_msg = "Hashcat 不支持 .cap 文件！请重新执行捕获以生成 .hc22000 文件。"
                self.logs = [f"[ERROR] {err_msg}"]
                return {"status": "error", "message": "缺少 .hc22000 文件"}

        hs_path = (self.captures_dir / target_file).resolve()
        wl_path = (self.wordlists_dir / wordlist_file).resolve()

        if not hs_path.exists():
            return {"status": "error", "message": f"文件缺失: {target_file}"}

        # === 2. 确定 Hashcat 路径 ===
        hashcat_exe = None
        work_dir = self.backend_root # 默认值
        
        # 优先读取 .env 配置
        if settings.HASHCAT_PATH and os.path.exists(settings.HASHCAT_PATH):
            hashcat_exe = settings.HASHCAT_PATH
            work_dir = os.path.dirname(hashcat_exe) # 关键：获取安装目录
        elif shutil.which("hashcat"):
            hashcat_exe = shutil.which("hashcat")
            work_dir = os.path.dirname(hashcat_exe)
            
        if not hashcat_exe:
            return {"status": "error", "message": "未找到 Hashcat，请检查 backend/.env 配置"}

        # === 3. 构造命令 ===
        mode = "22000" # 强制 WPA 模式
        
        cmd = [
            hashcat_exe,
            "-m", mode,
            "-a", "0",
            str(hs_path),
            str(wl_path),
            "--status",
            "--status-timer=1",
            "--force",
            "--potfile-disable"
        ]

        try:
            print(f"[DEBUG] Hashcat CWD: {work_dir}")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=work_dir # 【关键修复】在 Hashcat 目录下运行，解决 OpenCL 问题
            )
            self.is_running = True
            
            # 初始化状态
            self.crack_status = { "state": "Initializing", "progress": 0, "speed": "0 H/s", "eta": "Calculating...", "recovered": "0/0" }
            self.logs.append(f"[SYSTEM] 任务启动... Mode: {mode}")
            self.current_task = {"handshake": target_file, "wordlist": wordlist_file}

            threading.Thread(target=self._read_logs, daemon=True).start()
            
            return {"status": "success", "message": "启动成功"}
        except Exception as e:
            self.is_running = False
            return {"status": "error", "message": str(e)}

    def stop_crack(self):
        if self.process and self.is_running:
            self.process.terminate()
            self.is_running = False
            self.crack_status["state"] = "Stopped"
            self.logs.append("\n[SYSTEM] 用户停止。")
            return {"status": "success"}
        return {"status": "ignored"}

    def _read_logs(self):
        try:
            for line in self.process.stdout:
                line = line.strip()
                self.logs.append(line)
                if len(self.logs) > 500: self.logs.pop(0)
                
                # 解析状态
                if line.startswith("Status"): 
                    self.crack_status["state"] = line.split(":")[-1].strip()
                if "Speed" in line and "H/s" in line:
                    self.crack_status["speed"] = line.split(":")[-1].strip()
                if line.startswith("Progress"):
                    match = re.search(r'\(([\d\.]+)\%\)', line)
                    if match: self.crack_status["progress"] = float(match.group(1))
                if line.startswith("Time.Estimated"):
                    parts = line.split(")")
                    if len(parts) > 1: self.crack_status["eta"] = parts[0].split("(")[-1]
                if line.startswith("Recovered"):
                    self.crack_status["recovered"] = line.split(":")[1].split("(")[0].strip()

            self.process.wait()
            self.is_running = False
            self.crack_status["state"] = "Finished"
            
            if self.process.returncode == 0:
                self.logs.append("[SYSTEM] 破解完成！")
            else:
                self.logs.append(f"[SYSTEM] 进程退出 (Code: {self.process.returncode})")
                
        except Exception as e:
            self.is_running = False
            self.logs.append(f"[ERROR] {e}")

cracker = CrackEngine()