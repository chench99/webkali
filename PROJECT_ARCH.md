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

## 3. 🧠 核心业务流 (不可简化)

### ✅ 3.1. 自动化部署 (SSH 横向移动)

- **触发**: 后端 `main.py` 启动 -> `lifespan` 事件。
- **流程**:
  1. 读取 `.env` 中的 Kali 凭证。
  2. `ssh_manager` 连接 Kali。
  3. 检查 `/home/kali/wifi_scanner.py` 是否存在。
  4. **不存在则上传** `backend/kali_payloads/wifi_scanner.py`。
  5. 检查进程，未运行则执行 `nohup python3 wifi_scanner.py &`。

### ✅ 3.2. C2 扫描闭环 (HTTP 异步)

- **场景**: 用户在前端点击“扫描”。
- **流程**:
  1. **前端**: `POST /wifi/scan/start` (带 `interface`)。
  2. **后端**:
     - **不执行扫描**。
     - 将任务标记为 `current_task = 'scan'`。
     - 进入 `asyncio.Event.wait()` 阻塞状态。
  3. **Kali Agent**:
     - 死循环每 2 秒访问 `GET /agent/heartbeat`。
     - 领到 `scan` 任务。
     - 调用 `nmcli/iw` 扫描。
     - 结果 `POST` 回传至 `/callback`。
  4. **后端**: 收到回调 -> 存入内存 `c2_state` -> 解除阻塞。
  5. **前端**: 收到响应 -> 渲染列表 (包含“在线终端”列)。

### ✅ 3.3. 强攻模式 (SSH 同步)

- **场景**: Deauth 攻击 / 部署钓鱼热点。
- **流程**:
  1. **前端**: `POST /attack/eviltwin/start`。
  2. **后端**:
     - `ssh_manager` 建立连接。
     - 定位本地 `kali_payloads/fake_ap.py`。
     - SFTP 上传至 Kali `/tmp/`。
     - 执行 `chmod +x` 并 `nohup` 运行。
  3. **反馈**: 立即返回 `PID` 或日志路径。

### ✅ 3.4. AI 战术分析

- **场景**: 目标分析。
- **流程**:
  1. **前端**: 发送 SSID/加密方式 给 `/attack/ai/analyze_target`。
  2. **后端**: `ai_service.py` 组装 Prompt (Mode='attack')。
  3. **AI**: 输出包含 `<think>` 标签的深度思考过程。
  4. **前端**: 解析 `<think>`，渲染为灰色思维链区域。

------

## 4. 🛡️ 关键文件指纹 (Feature Lock)

**修改代码时，必须确保以下特征不丢失：**

#### `backend/app/api/v1/endpoints/wifi.py`

- [x] **内存数据库**: `c2_state` (存 Agent 网卡/心跳时间)。
- [x] **心跳接口**: `agent_heartbeat` (分发任务)。
- [x] **回调接口**: `callback` (接收数据)。
- [x] **下载接口**: `download_payload` (提供脚本下载)。

#### `backend/kali_payloads/wifi_scanner.py`

- [x] **守护模式**: `while True` 死循环。
- [x] **真实网卡**: 使用 `iw dev` 或 `ip link` 获取真实驱动名 (如 `rtl88xxau`)。
- [x] **双模扫描**: 同时支持 `nmcli` (Managed) 和 `iw` (Monitor)。
- [x] **自动回传**: 必须 POST 回 C2 地址。

#### `frontend/src/views/WiFiPanel.vue`

- [x] **C2 状态栏**: 顶部显示 Server/Agent 在线状态、在线人数。
- [x] **真实下拉框**: 显示 Agent 上报的网卡 (`wlan0 [Monitor]`)。
- [x] **全字段列表**: ESSID, BSSID, 厂商, 信道, 加密, **在线终端**, 信号, 情报。
- [x] **下载链接**: 提供 "下载 Payload" 按钮。

------

## 5. 📝 开发守则

1. **禁止本地扫描**: 后端代码永远不要尝试调用 `netsh` 或 Windows `subprocess` 进行扫描。一切无线操作**必须**下发给 Kali。
2. **路径一致性**: 所有下发给 Kali 的脚本，源码必须放在 `backend/kali_payloads/` 中。
3. **UI 完整性**: 修改前端时，不得删除“在线人数”、“客户端数量”等关键指标。
4. **接口兼容**: 新增功能需同时更新 `wifi.py` (任务分发) 和 `wifi_scanner.py` (任务执行)。