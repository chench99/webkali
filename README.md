# 🐉 Kali-C2-Platform (Hybrid Architecture)

**🛡️ Windows (Host) + Kali (Agent) 混合架构：一站式自动化渗透测试指挥平台**

![Status](https://img.shields.io/badge/Status-Alpha-orange)
![Python](https://img.shields.io/badge/Backend-FastAPI-green)
![Vue](https://img.shields.io/badge/Frontend-Vue3-blue)
![Database](https://img.shields.io/badge/DB-MySQL_8.0-blue)

## 📖 项目简介
Kali-C2-Platform 是一个现代化的混合 C2 平台，创新性地采用了 **"Windows 主控 + Kali 节点"** 的架构：
* **Windows 主控端:** 负责运行 Web 服务、MySQL 数据库、DeepSeek AI 推理以及 Hashcat GPU 密码破解。
* **Kali 节点端:** 通过 SSH 接收指令，负责底层发包、Nmap/Aircrack-ng/WiFi 扫描与攻击等红队任务。

## 🚀 核心功能
* **👁️ 资产侦察:** 全自动 Nmap/Masscan 扫描，自动指纹识别，AI 漏洞分析。
* **📡 无线渗透:** AX1800 网卡驱动支持，支持 Deauth 攻击、双子星钓鱼、握手包抓取。
* **🔓 密码破解:** 自动化回传 Kali 抓取的握手包至 Windows，调用 RTX 显卡加速破解。
* **🧠 AI 参谋:** 内置 DeepSeek API，智能分析目标漏洞、生成字典工单。
* **🎣 钓鱼工程:** 快速部署强制认证门户 (Captive Portal) 与 DNS 投毒模块。
* **💥 压力测试:** 支持 L3/L4 DDoS 模拟及 WiFi 协议压测。

## 🛠️ 环境要求

### Windows 端 (Server)
* Python 3.10+
* Node.js 16+
* MySQL 8.0+
* Hashcat (需配置路径)
* Npcap (用于 Scapy 发包)

### Kali 端 (Agent)
* 开启 SSH 服务 (`sudo systemctl start ssh`)
* 依赖工具: `nmap`, `masscan`, `aircrack-ng`, `hostapd`, `dnsmasq`, `mdk4`, `hcxpcapngtool`

## 📦 快速启动

### 1. 后端服务 (Windows)
```powershell
cd backend
# 首次启动请配置 .env 文件 (参考 .env.example)
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# 初始化数据库
python -c "from app.core.database import init_db; init_db()"

# 启动 API 服务
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### 2. 前端界面 (Windows)
```powershell
cd frontend
npm install
npm run dev
```

### 3. Agent 连接
* 确保 Kali 虚拟机/物理机与 Windows 网络互通。
* 在 `.env` 中配置 Kali 的 IP、SSH 用户名与密码。
* 后端启动后会自动尝试连接 Kali 并部署 Payload。

## ⚠️ 免责声明
本工具仅用于授权的安全测试与教育目的。请勿用于非法用途。开发者不对任何非法使用造成的后果负责。
