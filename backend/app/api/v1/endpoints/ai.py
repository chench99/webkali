from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import re
from app.modules.ai_agent.service import ai_service 

router = APIRouter()

class ChatRequest(BaseModel):
    prompt: str
    mode: str = "general"

class TargetInfo(BaseModel):
    ssid: str
    bssid: str
    encryption: str

@router.post("/chat")
async def chat_with_ai(req: ChatRequest):
    if not req.prompt:
        raise HTTPException(status_code=400, detail="内容不能为空")
    answer_text = ai_service.chat(req.prompt, req.mode)
    return {"code": 200, "result": answer_text}

@router.post("/analyze_target")
async def analyze_target(target: TargetInfo):
    """
    [增强版] WiFi 目标战术分析接口
    """
    prompt = f"""
    你是黑客专家。请分析目标WiFi并给出JSON格式报告。
    目标: SSID={target.ssid}, 加密={target.encryption}
    
    必须返回纯JSON，格式如下:
    {{
        "risk_level": "高/中/低",
        "summary": "一句话总结",
        "advice": "分步骤攻击建议",
        "dict_rules": ["字典规则1", "字典规则2"]
    }}
    """
    
    try:
        # 1. 调用 AI
        raw_response = ai_service.chat(prompt, "security")
        
        # 2. 【关键修复】使用正则提取 JSON 部分，忽略所有 Markdown 标记
        match = re.search(r"\{[\s\S]*\}", raw_response)
        if match:
            json_str = match.group(0)
            analysis_result = json.loads(json_str)
            return analysis_result
        else:
            raise ValueError("未找到 JSON 对象")

    except Exception as e:
        print(f"[AI Error] {str(e)}")
        # 兜底返回，防止前端报错
        return {
            "risk_level": "解析错误",
            "summary": "AI 返回格式异常，请查看控制台日志",
            "advice": f"原始返回内容:\n{raw_response if 'raw_response' in locals() else str(e)}",
            "dict_rules": ["Error"]
        }