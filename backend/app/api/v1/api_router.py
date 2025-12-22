from fastapi import APIRouter
# 1. 引入所有模块 (包括 attack)
from app.api.v1.endpoints import system, wifi, ai, attack

api_router = APIRouter()

# 2. 注册路由
api_router.include_router(system.router, prefix="/system", tags=["System Status"])
api_router.include_router(wifi.router, prefix="/wifi", tags=["WiFi Penetration"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Advisor"])

# 3. 【关键修复】注册攻击模块，否则前端调用的 /attack/... 全是 404
api_router.include_router(attack.router, prefix="/attack", tags=["Attack Operations"])