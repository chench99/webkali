from fastapi import APIRouter
# 1. 引入所有模块
from app.api.v1.endpoints import system, wifi, ai, attack, crack

api_router = APIRouter()

# 2. 注册路由
api_router.include_router(system.router, prefix="/system", tags=["System Status"])
api_router.include_router(wifi.router, prefix="/wifi", tags=["WiFi Penetration"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Advisor"])
api_router.include_router(attack.router, prefix="/attack", tags=["Attack Operations"])
# 【新增】注册破解模块
api_router.include_router(crack.router, prefix="/crack", tags=["Password Cracking"])