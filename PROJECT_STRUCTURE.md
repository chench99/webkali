# WebKali C2 Platform - 项目架构说明书

## 📂 项目概览

WebKali 是一个基于 **C2 (Command & Control)** 架构的无线渗透测试平台。
* **服务端 (Server)**: 运行在 Windows/Docker 上，负责指令下发、数据存储和 AI 分析。
* **执行端 (Agent)**: 运行在 Kali Linux 上，负责执行真实的渗透脚本（Payload）。
* **控制台 (Client)**: Vue.js 前端，提供可视化的操作界面。

---

## 🏗️ 目录结构树

```text
Kali-C2-Platform/
├── backend/                        # [C2 服务端] Python FastAPI 后端
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/
│   │   │       │   ├── system.py   # 系统状态接口 (CPU/内存/在线人数)
│   │   │       │   ├── wifi.py     # [核心] WiFi C2 接口 (任务分发/数据接收/Agent管理)
│   │   │       │   └── ai.py       # AI 参谋部接口 (DeepSeek 对话)
│   │   │       ├── api.py          # 路由注册总表
│   │   │       └── __init__.py
│   │   ├── core/
│   │   │   └── config.py           # 配置加载 (.env 读取)
│   │   ├── modules/
│   │   │   ├── wifi/
│   │   │   │   └── attacker.py     # 攻击逻辑封装 (指令生成)
│   │   │   └── ai_agent/
│   │   │       └── service.py      # AI 服务逻辑 (Prompt工程/思维链)
│   │   └── main.py                 # 后端启动入口 (CORS 配置/App 启动)
│   ├── kali_payloads/              # [Agent 仓库] 存放 Kali 专用脚本
│   │   └── wifi_scanner.py         # 核心 Payload (守护进程/自动扫描/心跳回传)
│   ├── requirements.txt            # Python 依赖库
│   └── .env                        # 环境变量 (API Key 等)
│
├── frontend/                       # [C2 控制台] Vue.js 前端
│   ├── src/
│   │   ├── views/
│   │   │   ├── WiFi/
│   │   │   │   └── WiFiPanel.vue   # [核心] WiFi 渗透主界面 (全中文/网卡选择/C2状态)
│   │   │   └── AI/
│   │   │       └── AiAdvisor.vue   # AI 参谋部界面 (支持深度思考展示)
│   │   ├── App.vue                 # 根组件
│   │   └── main.js                 # Vue 入口
│   ├── package.json                # npm 依赖配置
│   └── vue.config.js               # 前端配置
│
└── README.md                       # 项目说明
```