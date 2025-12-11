from app.api.v1.endpoints import system, wifi, ai

# 注册 System
api_router.include_router(system.router, prefix="/system", tags=["System Status"])
# 注册 WiFi (注意 prefix="/wifi")
api_router.include_router(wifi.router, prefix="/wifi", tags=["WiFi Penetration"])
# 注册 AI
api_router.include_router(ai.router, prefix="/ai", tags=["AI Advisor"])