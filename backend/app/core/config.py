import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 1. 智能计算绝对路径
# 逻辑：当前文件 (config.py) -> core -> app -> backend (项目根目录)
# 这样无论你在哪里运行 python 命令，路径都是对的
CURRENT_FILE = Path(__file__).resolve()
BASE_DIR = CURRENT_FILE.parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

# 2. 【核心调试】打印路径状态 (启动时请留意控制台输出！)
print("-" * 50)
print(f"[DEBUG] Config File: {CURRENT_FILE}")
print(f"[DEBUG] Base Dir:    {BASE_DIR}")
print(f"[DEBUG] Target .env: {ENV_PATH}")
print(f"[DEBUG] Exists?:     {ENV_PATH.exists()}")
print("-" * 50)

# 3. 显式加载 .env 文件 (这比 Pydantic 自动加载更稳健)
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
else:
    print("[!!!] 警告：找不到 .env 文件，程序可能会崩溃！")
    print("[!!!] 请检查文件名是否为 .env.txt (Windows常见错误)")

class Settings(BaseSettings):
    PROJECT_NAME: str = "Kali-C2-Platform"
    API_V1_STR: str = "/api/v1"

    # Database (必须字段)
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # Kali SSH (必须字段)
    KALI_HOST: str
    KALI_PORT: int = 22
    KALI_USER: str
    KALI_PASS: str

    # System
    SECRET_KEY: str = "default_secret"
    DEBUG: bool = True

    # AI Config (带默认值，不会报错)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    class Config:
        # 即使上面 load_dotenv 加载了，这里保留配置也是好的
        env_file = str(ENV_PATH)
        env_file_encoding = 'utf-8'
        extra = "ignore"

# 实例化配置
try:
    settings = Settings()
    print("[SUCCESS] 配置加载成功！")
except Exception as e:
    print(f"[FATAL] 配置加载失败: {e}")
    # 重新抛出异常以便查看详情，但在那之前我们已经打印了足够多的调试信息
    raise e