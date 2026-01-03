from fastapi import APIRouter
from pathlib import Path
from pydantic import BaseModel  # <--- 必须导入这个
from app.core.config import settings
import os
import subprocess

router = APIRouter()


# 全局状态
class CrackState:
    process = None
    is_running = False
    log_file = Path("/tmp/hashcat.log")


state = CrackState()

# 路径配置
BACKEND_DIR = Path(__file__).resolve().parents[4]
HANDSHAKE_DIR = BACKEND_DIR / "captures"
HANDSHAKE_DIR.mkdir(parents=True, exist_ok=True)


# === 🔥 关键新增：定义请求模型 ===
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
                    "path": str(f.resolve()),  # 绝对路径
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

    return {"status": "success", "dir": str(wordlist_path), "files": files}


# 3. 启动破解 (已修复参数接收)
@router.post("/start")
async def start_crack(req: CrackRequest):  # <--- 这里改成了接收对象 req
    """启动 Hashcat 破解任务"""
    if state.is_running:
        return {"status": "error", "message": "任务已在运行中"}

    # 从对象中提取参数
    handshake_file = req.handshake_file
    wordlist_file = req.wordlist_file

    print(f"[DEBUG] Receive Start Crack: \nHandshake: {handshake_file}\nWordlist: {wordlist_file}")

    if not handshake_file or not os.path.exists(handshake_file):
        return {"status": "error", "message": f"握手包路径无效: {handshake_file}"}
    if not wordlist_file or not os.path.exists(wordlist_file):
        return {"status": "error", "message": f"字典路径无效: {wordlist_file}"}

    # Hashcat 命令
    cmd = [
        "hashcat",
        "-m", "22000",
        "-a", "0",
        "-w", "3",
        "--status",
        "--status-timer", "1",
        "--force",
        "-o", "/tmp/cracked.txt",
        handshake_file,
        wordlist_file
    ]

    try:
        with open(state.log_file, "w") as f:
            f.write(f"[SYSTEM] Starting Hashcat...\nCMD: {' '.join(cmd)}\n")

        state.process = subprocess.Popen(
            cmd,
            stdout=open(state.log_file, "a"),
            stderr=subprocess.STDOUT,
            text=True
        )
        state.is_running = True
        return {"status": "success", "pid": state.process.pid}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 4. 停止任务
@router.post("/stop")
async def stop_crack():
    if state.process:
        state.process.terminate()
        state.process = None
        state.is_running = False
        with open(state.log_file, "a") as f:
            f.write("\n[SYSTEM] Task Stopped by User.\n")
        return {"status": "success"}
    return {"status": "error", "message": "无运行任务"}


# 5. 获取日志
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
                            status["progress"] = int(parts[0].strip()) / int(parts[1].split("(")[0].strip()) * 100
        except:
            pass

    return {"status": status, "is_running": state.is_running, "logs": logs}