from pydantic_settings import BaseSettings


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

    # === 新增：AI 配置 ===
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    class Config:
        env_file = ".env"
        extra = "ignore"  # 忽略多余的字段，防止报错


settings = Settings()