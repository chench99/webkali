from fastapi import APIRouter, HTTPException, BackgroundTasks
from pathlib import Path
from app.core.config import settings
import os
import subprocess
import asyncio

router = APIRouter()


# 全局状态 (简单单例模式)
class CrackState:
    process = None
    is_running = False
    log_file = Path("/tmp/hashcat.log")


state = CrackState()

# 定义目录路径
# 逻辑：当前文件 -> endpoints -> v1 -> api -> app -> backend -> 项目根目录
BASE_DIR = Path(__file__).resolve().parents[5]
HANDSHAKE_DIR = BASE_DIR / "captures" / "handshakes"

# 确保握手包目录存在
HANDSHAKE_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/files/handshakes")
async def get_handshakes():
    """列出所有 .hc22000 和 .cap 握手包"""
    files = []
    if HANDSHAKE_DIR.exists():
        for f in HANDSHAKE_DIR.iterdir():
            if f.suffix in ['.hc22000', '.cap', '.pcap']:
                files.append({
                    "name": f.name,
                    "path": str(f.resolve()),
                    "size": f"{f.stat().st_size / 1024:.2f} KB"
                })
    return {"status": "success", "files": files}


@router.get("/files/wordlists")
async def get_wordlists():
    """列出所有字典文件 (支持 .env 配置路径)"""
    # 1. 从 settings 读取路径
    wordlist_path = Path(settings.WORDLIST_DIR)

    # 2. 如果配置的是相对路径，则基于 backend 根目录解析
    if not wordlist_path.is_absolute():
        wordlist_path = BASE_DIR / settings.WORDLIST_DIR

    # 3. 检查目录是否存在
    if not wordlist_path.exists():
        return {"status": "error", "msg": f"字典目录不存在: {wordlist_path}", "files": []}

    # 4. 扫描所有文件
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


@router.post("/start")
async def start_crack(handshake_file: str = "", wordlist_file: str = ""):
    """启动 Hashcat 破解任务"""
    if state.is_running:
        return {"status": "error", "message": "任务已在运行中"}

    if not os.path.exists(handshake_file) or not os.path.exists(wordlist_file):
        return {"status": "error", "message": "文件不存在"}

    # Hashcat 命令: 22000模式 (WPA-PBKDF2-PMKID+EAPOL)
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
        # 清理并初始化日志
        with open(state.log_file, "w") as f:
            f.write("[SYSTEM] Task Starting...\n")

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
    """停止任务"""
    if state.process and state.is_running:
        state.process.terminate()
        state.process = None
        state.is_running = False
        with open(state.log_file, "a") as f:
            f.write("\n[SYSTEM] Task Stopped by User.\n")
        return {"status": "success"}
    return {"status": "error", "message": "无运行任务"}


@router.get("/logs")
async def get_logs():
    """读取实时日志和状态"""
    logs = []
    status = {"state": "Idle", "speed": "0", "progress": 0}

    # 检查进程是否还在运行
    if state.process:
        if state.process.poll() is not None:
            state.is_running = False

    if state.log_file.exists():
        try:
            with open(state.log_file, "r", errors='ignore') as f:
                lines = f.readlines()
                logs = [l.strip() for l in lines[-50:]]  # 只返回最后50行

                # 简单解析状态
                for l in lines[-20:]:
                    if "Status..........." in l: status["state"] = l.split(":")[1].strip()
                    if "Speed.#1........." in l: status["speed"] = l.split(":")[1].strip()
                    if "Progress........." in l:
                        try:
                            parts = l.split(":")[1].split("/")
                            current = int(parts[0].strip())
                            total = int(parts[1].split("(")[0].strip())
                            if total > 0:
                                status["progress"] = round((current / total) * 100, 2)
                        except:
                            pass
        except:
            pass

    return {
        "status": "success",
        "is_running": state.is_running,
        "logs": logs,
        "status": status
    }