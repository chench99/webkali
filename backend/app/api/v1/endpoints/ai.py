from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
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
    """通用对话接口"""
    if not req.prompt:
        raise HTTPException(status_code=400, detail="内容不能为空")
    if getattr(ai_service, "client", None) is None:
        raise HTTPException(status_code=503, detail="未配置 DEEPSEEK_API_KEY")
    answer_text = ai_service.chat(req.prompt, req.mode)
    return {"code": 200, "result": answer_text}


@router.post("/analyze_target")
async def analyze_target(target: TargetInfo):
    """
    [新增] WiFi 目标战术分析接口
    强制 AI 返回 JSON 格式的分析结果
    """
    if getattr(ai_service, "client", None) is None:
        return {
            "risk_level": "未配置",
            "summary": "未配置 DEEPSEEK_API_KEY，无法进行 AI 分析。",
            "advice": "在 `backend/.env` 配置 `DEEPSEEK_API_KEY` 后重启后端。",
            "dict_rules": []
        }
    # 构造 Prompt，强制 AI 输出 JSON
    prompt = f"""
    你是网络安全专家。请分析以下 WiFi 目标并给出渗透测试建议。
    目标信息：
    - SSID: {target.ssid}
    - BSSID: {target.bssid}
    - 加密: {target.encryption}

    请务必只返回一段纯 JSON 代码，不要包含 markdown 格式标记或其他废话。
    JSON 格式要求如下：
    {{
        "risk_level": "高危/中危/低危",
        "summary": "简短的目标特征总结（50字以内）",
        "advice": "具体的攻击向量建议（换行显示）",
        "dict_rules": ["建议的字典规则1", "建议的字典规则2"]
    }}
    """

    try:
        # 调用 AI
        raw_response = ai_service.chat(prompt, "security")

        # 清洗数据，尝试提取 JSON
        # 有时候 AI 会包裹 ```json ... ```，需要清洗掉
        json_str = raw_response.replace("```json", "").replace("```", "").strip()

        # 解析 JSON
        analysis_result = json.loads(json_str)

        return analysis_result

    except json.JSONDecodeError:
        # 如果 AI 没返回 JSON，做个兜底
        print(f"[AI Error] 解析失败，原始返回: {raw_response}")
        return {
            "risk_level": "格式异常",
            "summary": "AI 返回格式异常，无法解析为 JSON。",
            "advice": raw_response,  # 把原始文本展示出来
            "dict_rules": ["默认字典"]
        }
    except Exception as e:
        print(f"[AI Error] {str(e)}")
        return {
            "risk_level": "分析中断",
            "summary": f"服务内部错误: {str(e)}",
            "advice": "请检查后端日志",
            "dict_rules": []
        }
