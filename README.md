# ?? Kali-C2-Platform (Hybrid Architecture)

**基于 Windows (Host) + Kali (Agent) 混合架构的下一代自动化渗透测试与红队指挥平台。**

![Status](https://img.shields.io/badge/Status-Alpha-orange)
![Python](https://img.shields.io/badge/Backend-FastAPI-green)
![Vue](https://img.shields.io/badge/Frontend-Vue3-blue)
![Database](https://img.shields.io/badge/DB-MySQL_8.0-blue)

## ? 项目简介
Kali-C2-Platform 是一个现代化的红队 C2 平台。它创新性地采用了 **"Windows 大脑 + Kali 触手"** 的架构：
* **Windows 宿主机:** 负责运行 Web 服务、MySQL 数据库、DeepSeek AI 分析以及 Hashcat GPU 暴力破解。
* **Kali 虚拟机:** 通过 SSH 接受指令，负责底层发包（Nmap/Aircrack-ng）、WiFi 监听与中间人攻击。

## ? 核心功能
* **? 资产测绘:** 全自动 Nmap/Masscan 扫描，自动入库，AI 漏洞关联。
* **? 无线渗透:** AX1800 高性能网卡驱动，支持 Deauth 攻击、双子热点钓鱼、握手包抓取。
* **? 混合破解:** 自动将 Kali 抓到的握手包回传至 Windows，利用 RTX 显卡加速破解。
* **? AI 参谋:** 集成 DeepSeek API，智能分析服务漏洞、生成社工字典。
* **? 社工钓鱼:** 内置多模板强制门户 (Captive Portal) 与 DNS 劫持模块。
* **? 压力测试:** 支持 L3/L4 DDoS 模拟及 WiFi 协议层压测。

## ?? 环境依赖

### Windows 端 (Server)
* Python 3.10+
* Node.js 16+
* MySQL 8.0+
* Hashcat (已内置工具目录)
* Npcap (用于 Scapy 发包)

### Kali 端 (Agent)
* 开启 SSH 服务 (`sudo systemctl start ssh`)
* 工具链: `nmap`, `masscan`, `aircrack-ng`, `hostapd`, `dnsmasq`, `mdk4`

## ? 快速启动

### 1. 后端启动 (Windows)
```powershell
cd backend
# 首次运行需配置 .env 文件
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
# 初始化数据库
python -c "from app.core.database import init_db; init_db()"
# 启动 API 服务
uvicorn main:app --reload --host 0.0.0.0
```