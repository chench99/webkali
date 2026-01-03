from fastapi import APIRouter
from pathlib import Path
from pydantic import BaseModel  # <--- 必须引入这个
from app.core.config import settings
import os
import subprocess

router = APIRouter()


# 状态管理
class CrackState:
    process = None
    is_running = False
    log_file = Path("/tmp/hashcat.log")


state = CrackState()

# 路径定位
BACKEND_DIR = Path(__file__).resolve().parents[4]
HANDSHAKE_DIR = BACKEND_DIR / "captures"
HANDSHAKE_DIR.mkdir(parents=True, exist_ok=True)


# === 🔥 关键修复：定义请求体模型 ===
# 只有定义了这个，FastAPI 才知道要去读 JSON Body
class CrackRequest(BaseModel):
    handshake_file: str
    wordlist_file: str


@router.get("/files/handshakes")
async def get_handshakes():
    files = []
    if HANDSHAKE_DIR.exists():
        for f in HANDSHAKE_DIR.iterdir():
            if f.is_file() and f.suffix in ['.hc22000', '.cap', '.pcap']:
                files.append({
                    "name": f.name,
                    "path": str(f.resolve()),  # 传回绝对路径
                    "size": f"{f.stat().st_size / 1024:.2f} KB"
                })
    # 按时间排序，最新的在前面
    files.sort(key=lambda x: os.path.getmtime(x['path']), reverse=True)
    return {"status": "success", "files": files}


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
                    "path": str(f.resolve()),  # 传回绝对路径
                    "size": f"{f.stat().st_size / (1024 * 1024):.2f} MB"
                })
    except Exception as e:
        return {"status": "error", "msg": str(e), "files": []}
    return {"status": "success", "dir": str(wordlist_path), "files": files}


# === 🔥 关键修复：使用模型接收参数 ===
@router.post("/start")
async def start_crack(req: CrackRequest):
    """启动 Hashcat"""
    if state.is_running:
        return {"status": "error", "message": "任务已在运行中"}

    # 从对象中取值，防止取到空字符串
    handshake_file = req.handshake_file
    wordlist_file = req.wordlist_file

    print(f"[DEBUG] Start Crack -> Handshake: {handshake_file} | Wordlist: {wordlist_file}")

    if not handshake_file or not os.path.exists(handshake_file):
        return {"status": "error", "message": f"握手包路径无效 (File Not Found): {handshake_file}"}
    if not wordlist_file or not os.path.exists(wordlist_file):
        return {"status": "error", "message": f"字典路径无效 (File Not Found): {wordlist_file}"}

    # 构造命令
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