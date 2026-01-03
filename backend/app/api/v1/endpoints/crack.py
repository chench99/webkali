from fastapi import APIRouter
from pathlib import Path
from pydantic import BaseModel
from app.core.config import settings
import os
import subprocess
import tempfile  # <--- 关键引入：自动获取系统临时目录

router = APIRouter()


# === 状态管理 ===
class CrackState:
    process = None
    is_running = False
    # 使用 tempfile.gettempdir() 自动获取 Windows/Linux 正确的临时路径
    log_file = Path(tempfile.gettempdir()) / "webkali_hashcat.log"
    output_file = Path(tempfile.gettempdir()) / "webkali_cracked.txt"


state = CrackState()

# === 路径配置 ===
# 逻辑：当前文件 -> endpoints -> v1 -> api -> app -> backend
BACKEND_DIR = Path(__file__).resolve().parents[4]
HANDSHAKE_DIR = BACKEND_DIR / "captures"
HANDSHAKE_DIR.mkdir(parents=True, exist_ok=True)


# === 请求模型 ===
class CrackRequest(BaseModel):
    handshake_file: str
    wordlist_file: str


# 1. 获取握手包接口
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


# 2. 获取字典接口
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


# 3. 启动破解接口
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

    # 构造 Hashcat 命令
    # 注意：Windows下运行 Hashcat 需要确保 'hashcat' 已添加到环境变量 PATH 中
    # 或者将下面的 "hashcat" 改为绝对路径，如 "G:\\tools\\hashcat.exe"
    cmd = [
        "hashcat",
        "-m", "22000",
        "-a", "0",
        "-w", "3",
        "--status",
        "--status-timer", "1",
        "--force",
        "-o", str(state.output_file),  # 使用兼容路径
        handshake_file,
        wordlist_file
    ]

    try:
        # 确保日志文件可以被创建
        with open(state.log_file, "w") as f:
            f.write(f"[SYSTEM] Starting Task...\nCMD: {' '.join(cmd)}\n")

        state.process = subprocess.Popen(
            cmd,
            stdout=open(state.log_file, "a"),
            stderr=subprocess.STDOUT,
            text=True
        )
        state.is_running = True
        return {"status": "success", "pid": state.process.pid}
    except Exception as e:
        return {"status": "error", "message": f"启动失败: {str(e)}"}


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
                                if tot > 0:
                                    status["progress"] = round(cur / tot * 100, 1)
                            except:
                                pass
        except:
            pass

    return {"status": status, "is_running": state.is_running, "logs": logs}