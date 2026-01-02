from fastapi import APIRouter
from pydantic import BaseModel
from app.modules.crack.engine import cracker

router = APIRouter()

class CrackRequest(BaseModel):
    handshake_file: str
    wordlist_file: str

@router.get("/files/handshakes")
async def list_handshakes():
    files = cracker.get_files('handshake')
    return {"files": files}

@router.get("/files/wordlists")
async def list_wordlists():
    files = cracker.get_files('wordlist')
    return {"files": files}

@router.post("/start")
async def start_crack(req: CrackRequest):
    return cracker.start_crack(req.handshake_file, req.wordlist_file)

@router.post("/stop")
async def stop_crack():
    return cracker.stop_crack()

@router.get("/logs")
async def get_crack_logs():
    return {
        "is_running": cracker.is_running,
        "logs": cracker.logs,
        "task": cracker.current_task,
        "status": cracker.crack_status # 返回解析后的状态
    }