from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db
from app.api.v1.api_router import api_router


# === 新版启动事件写法 (Lifespan) ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 启动时执行
    print(f"--- 系统启动中: {settings.PROJECT_NAME} ---")
    try:
        init_db()  # 初始化 MySQL
        print("--- 数据库连接成功 ---")
    except Exception as e:
        print(f"!!! 数据库连接失败: {e}")

    yield  # 程序运行中...

    # 2. 关闭时执行 (可选)
    print("--- 系统关闭 ---")


# 初始化 FastAPI
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# 允许跨域 (让 Vue 前端能访问)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    return {"message": "Kali-C2-Platform Online", "docs": "/docs"}


if __name__ == "__main__":
    # 端口设置为 8001
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)