from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 使用 SQLite 数据库，文件名为 sql_app.db
SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

# 创建引擎
# check_same_thread=False 是 SQLite 必须的配置，允许在不同线程中使用连接
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)