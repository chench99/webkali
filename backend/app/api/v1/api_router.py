from fastapi import APIRouter

# 1. 一次性导入所有需要的模块
# 注意：确保 system.py, wifi.py, ai.py 都在 endpoints 文件夹里
from app.api.v1.endpoints import system, wifi, ai

# 如果你确实有一个单独的 attack.py 文件，请取消下面这行的注释
# from app.api.v1.endpoints import attack

api_router = APIRouter()

# ===========================
# 2. 注册各个模块的路由
# ===========================

# System 模块 (系统状态)
api_router.include_router(system.router, prefix="/system", tags=["System Status"])

# WiFi 模块 (扫描、握手包捕获、攻击)
# 注意：在你之前的代码中，攻击逻辑(capture/start)是写在 wifi.py 里的
# 所以这里注册了 wifi.router 后，前端访问 /api/v1/wifi/capture/start 就能通了
api_router.include_router(wifi.router, prefix="/wifi", tags=["WiFi Penetration"])

# AI 模块 (DeepSeek 对话)
api_router.include_router(ai.router, prefix="/ai", tags=["AI Advisor"])

# Attack 模块 (仅当你有一个独立的 attack.py 文件时才启用)
# api_router.include_router(attack.router, prefix="/attack", tags=["Attack"])