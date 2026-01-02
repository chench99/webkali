import random


class AIService:
    def analyze_wifi_target(self, ssid: str, encryption: str, vendor: str = "Unknown") -> dict:
        """
        模拟 AI 分析或调用真实 LLM
        """
        # 这里你可以接入真实的 DeepSeek/OpenAI API
        # 为了防止前端 undefined，我们这里先返回一个标准的 Mock 结构

        # 简单的规则引擎
        risk = "低 (Low)"
        advice = "该目标安全性较高。"

        if "WEP" in encryption.upper() or "OPEN" in encryption.upper():
            risk = "极高 (Critical)"
            advice = "目标使用过时加密协议 (WEP/Open)，可直接通过 ARP 重放攻击在 5 分钟内破解。"
        elif "WPA" in encryption.upper():
            risk = "中 (Medium)"
            advice = f"目标使用 {encryption}。建议步骤：\n1. 启动 Handshake 捕获。\n2. 使用 Deauth 强制客户端重连。\n3. 获取握手包后使用 Hashcat 跑字典。"

        return {
            "risk_level": risk,
            "summary": f"针对 {ssid} 的战术分析已完成。",
            "advice": advice,
            "dict_rules": ["弱口令 Top100", "SSID 组合", "手机号段"]
        }


ai_service = AIService()