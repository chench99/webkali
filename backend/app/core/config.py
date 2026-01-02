from pydantic_settings import BaseSettings
from pathlib import Path
import os

# 自动定位到 backend 根目录
# __file__ 是 config.py, parent是 core, parent.parent 是 app, parent.parent.parent 是 backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Kali-C2-Platform"
    API_V1_STR: str = "/api/v1"

    # Database
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # Kali SSH
    KALI_HOST: str
    KALI_PORT: int = 22
    KALI_USER: str
    KALI_PASS: str

    # System
    SECRET_KEY: str = "default_secret"
    DEBUG: bool = True

    # AI Config
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    class Config:
        # 使用绝对路径，确保无论在哪里运行 main.py 都能找到 .env
        env_file = os.path.join(BASE_DIR, ".env")
        env_file_encoding = 'utf-8'
        extra = "ignore"  # 忽略多余字段

settings = Settings()