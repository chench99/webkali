from fastapi import APIRouter
from pathlib import Path
from pydantic import BaseModel
from app.core.config import settings  # <--- 这里现在包含了您的 HASHCAT_PATH
import os
import subprocess
import tempfile

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


# 3. 启动破解 (关键修复)
@router.post("/start")
async def start_crack(req: CrackRequest):
    if state.is_running:
        return {"status": "error", "message": "任务已在运行中"}

    handshake_file = req.handshake_file
    wordlist_file = req.wordlist_file

    if not os.path.exists(handshake_file):
        return {"status": "error", "message": f"握手包不存在: {handshake_file}"}
    if not os.path.exists(wordlist_file):
        return {"status": "error", "message": f"字典不存在: {wordlist_file}"}

    # 🔥🔥🔥 核心修改：直接从配置读取您定义的路径 🔥🔥🔥
    hashcat_cmd = settings.HASHCAT_PATH

    # 自动计算工作目录 (解决 OpenCL not found 问题)
    # 如果您配置的是 "hashcat" (命令)，工作目录就为 None (由系统决定)
    # 如果您配置的是 "G:\tools\hashcat.exe" (绝对路径)，工作目录就是 "G:\tools"
    working_dir = None
    if os.path.isabs(hashcat_cmd):
        working_dir = os.path.dirname(hashcat_cmd)

    # 打印调试信息，让您知道它到底读到了什么
    print(f"[DEBUG] Configured Hashcat Path: {hashcat_cmd}")
    print(f"[DEBUG] Calculated Working Dir: {working_dir}")

    cmd = [
        hashcat_cmd,
        "-m", "22000",
        "-a", "0",
        "-w", "3",
        "--status",
        "--status-timer", "1",
        "--force",
        "-S",  # 允许慢速核心
        "-o", str(state.output_file),
        handshake_file,
        wordlist_file
    ]

    try:
        with open(state.log_file, "w") as f:
            f.write(f"[SYSTEM] Starting Task...\nCMD: {' '.join(cmd)}\nCWD: {working_dir}\n")

        state.process = subprocess.Popen(
            cmd,
            cwd=working_dir,  # 🔥 关键：在这里切换目录
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


# 5. 日志接口
@router.get("/logs")
async def get_logs():
    logs = []
    status = {"state": "Idle", "speed": "0 H/s", "progress": 0}

    if state.process and state.process.poll() is not None:
        state.is_running = False

    if state.log_file.exists():
        try:
            with open(state.log_file, "r", errors='ignore') as f:
                lines = f.readlines()
                logs = [l.strip() for l in lines[-50:]]
                for l in lines[-30:]:
                    if "Status..........." in l: status["state"] = l.split(":")[1].strip()
                    if "Speed.#1........." in l: status["speed"] = l.split(":")[1].strip()
                    if "Progress........." in l:
                        parts = l.split(":")[1].split("/")
                        if len(parts) > 1:
                            try:
                                cur = int(parts[0].strip())
                                tot = int(parts[1].split("(")[0].strip())
                                if tot > 0: status["progress"] = round(cur / tot * 100, 1)
                            except:
                                pass
        except:
            pass

    return {"status": status, "is_running": state.is_running, "logs": logs}