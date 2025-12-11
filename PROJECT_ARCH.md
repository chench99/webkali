# 🏛️ WebKali C2 Platform - 核心架构备忘录 (v5.0)

> **⚠️ 严正声明：** 本文档是项目的“宪法”。后续任何开发、代码修改或功能扩展，必须严格遵循本文档定义的架构逻辑、文件职责和数据流向。**严禁简化逻辑或破坏 C2 闭环。**

---

## 1. 🔭 宏观架构 (Hybrid C2 Architecture)

本项目采用 **Windows 服务端 (Server) + Kali 执行端 (Agent)** 的混合双引擎架构。

| 组件                | 运行环境            | 核心职责                                           | 通信方式                         |
| :------------------ | :------------------ | :------------------------------------------------- | :------------------------------- |
| **控制台 (Client)** | 浏览器 (Vue3)       | 可视化交互、指令下发、数据展示                     | HTTP / WebSocket                 |
| **服务端 (Server)** | Windows (FastAPI)   | 任务调度、数据存储、AI 分析、Hashcat 破解          | -                                |
| **执行端 (Agent)**  | Kali Linux (Python) | **驻留进程**，执行底层渗透命令 (nmcli/iw/aireplay) | HTTP (心跳回传) + SSH (直连攻击) |

---

## 2. 📂 项目目录结构标准

```text
Kali-C2-Platform/
├── backend/                        # [Server] Windows 后端
│   ├── app/
│   │   ├── api/v1/endpoints/
│   │   │   ├── wifi.py             # [核心] C2 指挥中枢 (心跳/任务分发/回调)
│   │   │   ├── attack.py           # [核心] 攻击控制器 (SSH 直连/钓鱼/AI分析)
│   │   │   ├── system.py           # 系统状态 (CPU/内存/在线人数)
│   │   │   └── ai.py               # AI 接口 (DeepSeek 深度思考)
│   │   ├── core/
│   │   │   ├── ssh_manager.py      # [核心] SSH 通道管理 (上传/执行)
│   │   │   └── database.py         # MySQL 连接池
│   │   ├── modules/
│   │   │   ├── wifi/attacker.py    # 攻击逻辑封装
│   │   │   └── ai_agent/service.py # AI 逻辑 (Prompt 工程)
│   │   └── main.py                 # 启动入口 (Lifespan/CORS)
│   ├── kali_payloads/              # [Payload 仓库]
│   │   └── wifi_scanner.py         # [Agent] 核心守护进程 (自动扫描/回传)
│   ├── .env                        # 配置文件 (Kali IP/User/Pass, DB Info)
│   └── requirements.txt
│
├── frontend/                       # [Client] Vue3 前端
│   ├── src/
│   │   ├── views/
│   │   │   ├── WiFiPanel.vue       # [核心] WiFi 控制台 (全中文/C2状态/真实网卡)
│   │   │   ├── AttackDetail.vue    # [核心] 单兵作战 (Deauth/钓鱼/AI分析)
│   │   │   ├── Dashboard.vue       # 仪表盘 (状态监控)
│   │   │   └── AIAssistant.vue     # AI 参谋部 (<think>标签渲染)
│   │   ├── api/index.js            # API 统一封装
│   │   └── ...
│   └── vite.config.js              # 代理配置 (转发 /api -> 8001)
│
└── PROJECT_ARCH.md                 # [本文档] 架构说明书
```