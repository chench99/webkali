# backend/app/api/v1/endpoints/crack.py

from fastapi import APIRouter, HTTPException
from pathlib import Path
from app.core.config import settings  # <--- 导入配置
import os

router = APIRouter()


@router.get("/files/wordlists")
async def get_wordlists():
    """列出配置目录下的字典文件"""
    # 1. 从 settings 读取路径
    wordlist_path = Path(settings.WORDLIST_DIR)

    # 2. 如果配置的是相对路径，则基于 backend 根目录解析
    if not wordlist_path.is_absolute():
        base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        wordlist_path = base_dir / settings.WORDLIST_DIR

    # 3. 检查目录是否存在
    if not wordlist_path.exists():
        return {"status": "error", "msg": f"字典目录不存在: {wordlist_path}", "files": []}

    # 4. 扫描 .txt 文件
    files = []
    try:
        for f in wordlist_path.iterdir():
            if f.is_file() and f.suffix == '.txt':
                files.append({
                    "name": f.name,
                    "path": str(f.resolve()),  # 返回绝对路径给 Hashcat 用
                    "size": f"{f.stat().st_size / (1024 * 1024):.2f} MB"
                })
    except Exception as e:
        return {"status": "error", "msg": str(e), "files": []}

    return {"status": "success", "dir": str(wordlist_path), "files": files}