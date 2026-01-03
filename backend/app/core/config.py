import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# =========================================================
# 1. 智能计算绝对路径
# =========================================================
# 逻辑：当前文件(config.py) -> core -> app -> backend (项目根目录)
CURRENT_FILE = Path(__file__).resolve()
BASE_DIR = CURRENT_FILE.parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

# 调试信息 (方便排查路径问题)
print(f"[Config] Loading .env from: {ENV_PATH}")

# =========================================================
# 2. 强制加载环境变量
# =========================================================
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
else:
    print(f"[Config] ⚠️ Warning: .env file not found at {ENV_PATH}")
    print(f"[Config] System will rely on environment variables or defaults.")

# =========================================================
# 3. 定义配置类
# =========================================================
class Settings(BaseSettings):
    # --- 项目基础信息 ---
    PROJECT_NAME: str = "Kali-C2-Platform"
    API_V1_STR: str = "/api/v1"

    # --- 数据库配置 (必须与 .env 一致) ---
    DB_HOST: str
    DB_PORT: int = 3306
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    # --- Kali Agent 配置 (必须与 .env 一致) ---
    KALI_HOST: str
    KALI_PORT: int = 22
    KALI_USER: str
    KALI_PASS: str

    # --- 系统安全与调试 ---
    SECRET_KEY: str = "default_insecure_key_please_change"
    DEBUG: bool = True

    # --- 字典与文件路径 (新增) ---
    # 默认为项目根目录下的 wordlists 文件夹
    # 您可以在 .env 中设置 WORDLIST_DIR=G:/xxx 来覆盖它
    WORDLIST_DIR: str = "wordlists"

    # 🔥🔥🔥 关键新增：Hashcat 路径配置 🔥🔥🔥
    # 如果 .env 里没写，默认为 "hashcat" (尝试系统命令)
    # 如果 .env 里写了 HASHCAT_PATH=G:/tools/hashcat.exe，这里就会自动读取
    HASHCAT_PATH: str = "hashcat"

    # --- AI 配置 (DeepSeek) ---
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    class Config:
        # 指定环境变量文件路径
        env_file = str(ENV_PATH)
        env_file_encoding = 'utf-8'
        # 允许 .env 中存在多余字段 (防止报错)
        extra = "ignore"
        # 大小写敏感设置
        case_sensitive = True

# =========================================================
# 4. 实例化导出
# =========================================================
try:
    settings = Settings()
    print("[Config] Configuration loaded successfully.")
    print(f"[Config] Hashcat Path: {settings.HASHCAT_PATH}") # 打印一下方便确认
except Exception as e:
    print(f"[Config] ❌ Critical Error: Failed to load settings.")
    print(f"Error details: {e}")
    # 重新抛出异常，防止程序在配置错误的情况下继续运行
    raise e