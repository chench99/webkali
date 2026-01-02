from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.pool import QueuePool
from app.core.config import settings

# === 关键修复：显式导入所有模型 ===
# 必须在这里导入，否则 SQLModel.metadata.create_all() 无法识别这些表
from app.models.wifi import WiFiNetwork, TargetedClient, DeepScanClient

# 构造 MySQL 连接字符串
DATABASE_URL = f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

# 创建引擎 (高性能配置)
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,          # 基础连接数
    max_overflow=10,       # 突发连接数
    pool_recycle=3600,     # 连接回收时间
    poolclass=QueuePool
)

def init_db():
    """初始化数据库表结构"""
    # 因为上面已经 import 了 app.models.wifi，所以 metadata 里现在有内容了
    SQLModel.metadata.create_all(engine)
    print(f"[*] MySQL Database Initialized: {settings.DB_HOST}")

def get_session():
    """依赖注入用的 Session 生成器"""
    with Session(engine) as session:
        yield session