from openai import OpenAI
from app.core.config import settings
import json


class AIService:
    def __init__(self):
        # 1. 检查 Key 是否配置
        if not settings.DEEPSEEK_API_KEY:
            print("[!] 警告: 未配置 DEEPSEEK_API_KEY，AI 功能将无法使用。")
            self.client = None
        else:
            # 2. 初始化客户端
            self.client = OpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL
            )

    # ----------------------------------------------------------------
    # [核心] 支持模式切换和深度思考的对话接口
    # ----------------------------------------------------------------
    def chat(self, prompt: str, mode: str = "general"):
        """
        :param mode: 'general' (普通), 'attack' (红队/深度), 'code' (代码/深度)
        """
        if not self.client:
            return "❌ 错误: 后端未配置 API Key。"

        # --- A. 普通模式 (快速、直接) ---
        if mode == "general":
            system_instruction = (
                "你是 WebKali 的智能助手。回答要简短、友好、直接。"
                "不要输出任何 XML 标签，直接回答用户的问题。"
            )
            max_tokens = 1000
            temperature = 0.7

        # --- B. 深度思考模式 (红队/代码) ---
        else:
            # 这里的 System Prompt 是关键：强制 AI 模拟思维链
            role_def = "你是红队战术专家" if mode == "attack" else "你是资深 Python 安全开发人员"

            system_instruction = f"""
            {role_def}。

            【深度思考协议已启动】
            在给出最终回复之前，你必须先进行深度的逻辑推演。

            请严格遵守以下输出格式（不要使用 Markdown 代码块包裹 XML）：

            <think>
            这里写出你的思考过程：
            1. 分析用户意图...
            2. 评估潜在风险...
            3. 制定战术/代码逻辑...
            </think>

            (在思考标签结束后，这里写出给用户的最终回答，包含具体的攻击方案或代码)
            """
            max_tokens = 2000  # 给思考过程留出更多 Token
            temperature = 0.6  # 稍微降低温度以保证逻辑严密

        try:
            print(f"[*] AI 请求 (Mode: {mode})...")

            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content
            return content

        except Exception as e:
            print(f"❌ [Chat Error]: {e}")
            return f"AI 接口请求失败: {str(e)}"

    # ----------------------------------------------------------------
    # [保留] 原有的 WiFi 分析方法
    # ----------------------------------------------------------------
    def analyze_wifi_target(self, ssid, encryption, vendor="Unknown"):
        # (为了节省篇幅，这里保持你原有的 analyze_wifi_target 代码不变)
        # ...
        if not self.client:
            return {"risk_level": "Error", "summary": "No Key", "dict_rules": []}

        prompt = f"分析 WiFi: {ssid}, 加密: {encryption}..."
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "只输出 JSON"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4
            )
            content = response.choices[0].message.content
            return json.loads(content.replace("```json", "").replace("```", "").strip())
        except Exception as e:
            return {"risk_level": "Error", "summary": str(e), "dict_rules": []}


ai_service = AIService()