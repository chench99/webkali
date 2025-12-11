# backend/app/api/v1/endpoints/ai.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.modules.ai_agent.service import ai_service # 引用我们刚才修好的 service

router = APIRouter()

class ChatRequest(BaseModel):
    prompt: str
    mode: str = "general"

@router.post("/chat")
async def chat_with_ai(req: ChatRequest):
    """
    AI 对话接口
    """
    if not req.prompt:
        raise HTTPException(status_code=400, detail="内容不能为空")

    # 1. 调用 Service 获取 AI 回复 (这是一个字符串)
    answer_text = ai_service.chat(req.prompt, req.mode)

    # 2. 【关键修改】把它包装成 JSON 返回，而不是直接返回字符串
    # 这样前端可以通过 response.data.result 拿到数据
    return {
        "code": 200,
        "status": "success",
        "result": answer_text 
    }