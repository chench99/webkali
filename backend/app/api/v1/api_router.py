from fastapi import APIRouter
# 确保导入路径正确，这三个模块必须在 app/api/v1/endpoints/ 目录下
from app.api.v1.endpoints import system, wifi, ai

# ======================================================
# 1. 【核心修复】必须先实例化 APIRouter 对象
#    报错 NameError 就是因为缺少了这一行！
# ======================================================
api_router = APIRouter()

# ======================================================
# 2. 然后才能使用它来注册子路由
# ======================================================

# 注册系统状态模块
api_router.include_router(system.router, prefix="/system", tags=["System Status"])

# 注册 WiFi 模块 (包含扫描和攻击)
api_router.include_router(wifi.router, prefix="/wifi", tags=["WiFi Penetration"])

# 注册 AI 模块 (包含深度思考)
api_router.include_router(ai.router, prefix="/ai", tags=["AI Advisor"])