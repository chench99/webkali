from fastapi import APIRouter
from pathlib import Path
from pydantic import BaseModel
from app.core.config import settings
import os
import subprocess

router = APIRouter()


# === 状态管理 ===
class CrackState:
    process = None
    is_running = False
    log_file = Path("/tmp/hashcat.log")


state = CrackState()

# === 路径配置 (与 attack.py 保持一致) ===
# 使用 Path.cwd() 确保与 attack.py 的保存路径对齐
HANDSHAKE_DIR = Path.cwd() / "captures"
HANDSHAKE_DIR.mkdir(parents=True, exist_ok=True)


# === 请求模型 (修复参数接收错误) ===
class CrackRequest(BaseModel):
    handshake_file: str
    wordlist_file: str


# 1. 获取握手包接口 (补全)
@router.get("/files/handshakes")
async def get_handshakes():
    files = []
    if HANDSHAKE_DIR.exists():
        for f in HANDSHAKE_DIR.iterdir():
            # 支持 .hc22000 (Hashcat专用) 和 .cap (需转换)
            if f.is_file() and f.suffix in ['.hc22000', '.cap', '.pcap']:
                files.append({
                    "name": f.name,
                    "path": str(f.resolve()),  # 绝对路径
                    "size": f"{f.stat().st_size / 1024:.2f} KB"
                })
    # 按修改时间倒序（最新的在前面）
    files.sort(key=lambda x: os.path.getmtime(x['path']), reverse=True)
    return {"status": "success", "files": files}


# 2. 获取字典接口
@router.get("/files/wordlists")
async def get_wordlists():
    # 优先使用配置的路径，默认回退到 backend/wordlists
    wordlist_path = Path(settings.WORDLIST_DIR)
    if not wordlist_path.is_absolute():
        wordlist_path = Path.cwd() / settings.WORDLIST_DIR

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


# 3. 启动破解接口 (补全)
@router.post("/start")
async def start_crack(req: CrackRequest):
    if state.is_running:
        return {"status": "error", "message": "任务已在运行中"}

    handshake_file = req.handshake_file
    wordlist_file = req.wordlist_file

    if not os.path.exists(handshake_file):
        return {"status": "error", "message": "握手包文件不存在"}
    if not os.path.exists(wordlist_file):
        return {"status": "error", "message": "字典文件不存在"}

    # 构造 Hashcat 命令 (适配 Kali)
    cmd = [
        "hashcat",
        "-m", "22000",  # 模式: WPA-PBKDF2-PMKID+EAPOL
        "-a", "0",  # 模式: 字典攻击
        "-w", "3",  # 负载: 高
        "--status",
        "--status-timer", "1",
        "--force",  # 必须加，防止虚拟机无显卡报错
        "-o", "/tmp/cracked.txt",
        handshake_file,
        wordlist_file
    ]

    try:
        # 写入启动日志
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
        return {"status": "error", "message": str(e)}


# 4. 停止接口 (补全)
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


# 5. 日志接口 (补全)
@router.get("/logs")
async def get_logs():
    logs = []
    status = {"state": "Idle", "speed": "0 H/s", "progress": 0}

    # 检查进程状态
    if state.process and state.process.poll() is not None:
        state.is_running = False

    if state.log_file.exists():
        try:
            with open(state.log_file, "r", errors='ignore') as f:
                lines = f.readlines()
                logs = [l.strip() for l in lines[-50:]]

                # 简易状态解析
                for l in lines[-30:]:
                    if "Status..........." in l: status["state"] = l.split(":")[1].strip()
                    if "Speed.#1........." in l: status["speed"] = l.split(":")[1].strip()
                    if "Progress........." in l:
                        parts = l.split(":")[1].split("/")
                        if len(parts) > 1:
                            try:
                                cur = int(parts[0].strip())
                                tot = int(parts[1].split("(")[0].strip())
                                status["progress"] = round(cur / tot * 100, 1)
                            except:
                                pass
        except:
            pass

    return {"status": status, "is_running": state.is_running, "logs": logs}