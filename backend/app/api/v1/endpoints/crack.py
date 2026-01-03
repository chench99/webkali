from fastapi import APIRouter
from pathlib import Path
from pydantic import BaseModel
from app.core.config import settings
import os
import subprocess
import tempfile
import shutil
import re  # <--- 新增正则模块，用于精准解析

router = APIRouter()


# === 状态管理 ===
class CrackState:
    process = None
    is_running = False
    log_file = Path(tempfile.gettempdir()) / "webkali_hashcat.log"
    output_file = Path(tempfile.gettempdir()) / "webkali_cracked.txt"


state = CrackState()

# === 路径配置 ===
BACKEND_DIR = Path(__file__).resolve().parents[4]
HANDSHAKE_DIR = BACKEND_DIR / "captures"
HANDSHAKE_DIR.mkdir(parents=True, exist_ok=True)


class CrackRequest(BaseModel):
    handshake_file: str
    wordlist_file: str


# 1. 获取握手包
@router.get("/files/handshakes")
async def get_handshakes():
    files = []
    if HANDSHAKE_DIR.exists():
        for f in HANDSHAKE_DIR.iterdir():
            if f.is_file() and f.suffix in ['.hc22000', '.cap', '.pcap']:
                files.append({
                    "name": f.name,
                    "path": str(f.resolve()),
                    "size": f"{f.stat().st_size / 1024:.2f} KB"
                })
    files.sort(key=lambda x: os.path.getmtime(x['path']), reverse=True)
    return {"status": "success", "files": files}


# 2. 获取字典
@router.get("/files/wordlists")
async def get_wordlists():
    wordlist_path = Path(settings.WORDLIST_DIR)
    if not wordlist_path.is_absolute():
        wordlist_path = BACKEND_DIR / settings.WORDLIST_DIR
    if not wordlist_path.exists():
        return {"status": "error", "msg": f"字典目录不存在: {wordlist_path}", "files": []}
    files = []
    try:
        for f in wordlist_path.iterdir():
            if f.is_file():
                files.append({
                    "name": f.name,
                    "path": str(f.resolve()),
                    "size": f"{f.stat().st_size / (1024 * 1024):.2f} MB"
                })
    except Exception as e:
        return {"status": "error", "msg": str(e), "files": []}
    return {"status": "success", "files": files}


# 3. 启动破解
@router.post("/start")
async def start_crack(req: CrackRequest):
    if state.is_running:
        return {"status": "error", "message": "任务已在运行中"}

    handshake_file = req.handshake_file
    wordlist_file = req.wordlist_file

    if not os.path.exists(handshake_file):
        return {"status": "error", "message": "握手包不存在"}
    if not os.path.exists(wordlist_file):
        return {"status": "error", "message": "字典不存在"}

    # 自动定位 Hashcat
    hashcat_cmd = settings.HASHCAT_PATH
    working_dir = None

    # 尝试寻找真实路径
    exe_path = shutil.which("hashcat")
    if exe_path:
        working_dir = os.path.dirname(exe_path)
    elif os.path.exists(hashcat_cmd) and os.path.isabs(hashcat_cmd):
        working_dir = os.path.dirname(hashcat_cmd)

    # 构造命令
    cmd = [
        hashcat_cmd,
        "-m", "22000",
        "-a", "0",
        "-w", "3",
        "--status",
        "--status-timer", "1",  # 每秒刷新状态
        "--force",
        "-S",  # 允许慢速核心(CPU)
        "-o", str(state.output_file),
        handshake_file,
        wordlist_file
    ]

    try:
        # 清空旧日志
        with open(state.log_file, "w") as f:
            f.write(f"[SYSTEM] Starting Task...\nCMD: {' '.join(cmd)}\n")

        state.process = subprocess.Popen(
            cmd,
            cwd=working_dir,
            stdout=open(state.log_file, "a"),
            stderr=subprocess.STDOUT,
            text=True
        )
        state.is_running = True
        return {"status": "success", "pid": state.process.pid}
    except Exception as e:
        return {"status": "error", "message": f"启动异常: {str(e)}"}


# 4. 停止接口
@router.post("/stop")
async def stop_crack():
    if state.process:
        state.process.terminate()
        state.process = None
        state.is_running = False
        with open(state.log_file, "a") as f:
            f.write("\n[SYSTEM] Stopped by user.\n")
        return {"status": "success"}
    return {"status": "error", "message": "无运行任务"}


# 5. 日志接口 (🔥 核心升级：增强解析逻辑)
@router.get("/logs")
async def get_logs():
    logs = []
    status = {
        "state": "Idle",
        "speed": "0 H/s",
        "progress": 0,
        "recovered": "0/0",
        "eta": "计算中..."
    }

    # 检查进程死活
    if state.process and state.process.poll() is not None:
        state.is_running = False

    if state.log_file.exists():
        try:
            # 1. 读取更多内容 (最后 8KB)，防止漏掉状态块
            file_size = state.log_file.stat().st_size
            read_size = min(file_size, 8192)  # 读取最后 8KB

            with open(state.log_file, "r", errors='ignore') as f:
                if file_size > read_size:
                    f.seek(file_size - read_size)
                content = f.read()

                # 分割日志用于前端显示 (只取最后 50 行)
                lines = content.splitlines()
                logs = lines[-50:]

                # 2. 倒序解析状态 (找到最新的那个状态块)
                # Hashcat 输出示例:
                # Speed.#1.........:    15000 H/s ...
                # Time.Estimated...: Sat Jan 03 17:00:00 2026 (8 mins, 40 secs)

                reversed_lines = list(reversed(lines))

                # === 提取速度 (Speed) ===
                for line in reversed_lines:
                    if "Speed.#1" in line:
                        # 格式: Speed.#1.........:    15000 H/s (5.33ms)...
                        parts = line.split(":")
                        if len(parts) > 1:
                            # 取 "15000 H/s"
                            status["speed"] = parts[1].split("(")[0].strip()
                        break

                # === 提取剩余时间 (ETA) ===
                for line in reversed_lines:
                    if "Time.Estimated" in line:
                        # 格式: ... (8 mins, 40 secs)
                        # 我们提取括号里的内容
                        if "(" in line:
                            status["eta"] = line.split("(")[-1].strip().rstrip(")")
                        else:
                            # 没括号可能是不显示时间或刚开始
                            status["eta"] = line.split(":")[-1].strip()
                        break

                # === 提取状态 (State) ===
                for line in reversed_lines:
                    if "Status..........." in line:
                        status["state"] = line.split(":")[1].strip()
                        break

                # === 提取恢复进度 (Recovered) ===
                for line in reversed_lines:
                    if "Recovered........" in line:
                        status["recovered"] = line.split(":")[1].split("(")[0].strip()
                        break

                # === 提取进度百分比 (Progress) ===
                for line in reversed_lines:
                    if "Progress........." in line:
                        # 格式: 123/456 (10.00%)
                        try:
                            parts = line.split(":")[1].split("/")
                            if len(parts) > 1:
                                current = int(parts[0].strip())
                                total = int(parts[1].split("(")[0].strip())
                                if total > 0:
                                    status["progress"] = round((current / total) * 100, 2)
                        except:
                            pass
                        break

        except Exception as e:
            print(f"[ERROR] Log parsing failed: {e}")

    return {"status": status, "is_running": state.is_running, "logs": logs}