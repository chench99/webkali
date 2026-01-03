from fastapi import APIRouter
from app.api.v1.endpoints import wifi, system, attack, crack  # <--- 必须导入 crack

api_router = APIRouter()

api_router.include_router(wifi.router, prefix="/wifi", tags=["wifi"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(attack.router, prefix="/attack", tags=["attack"])
api_router.include_router(crack.router, prefix="/crack", tags=["crack"]) # <--- 必须注册 crack