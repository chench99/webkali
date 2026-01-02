# � API 接口文档 (v1)

- Base URL：`/api/v1`
- Swagger：启动后端后访问 `http://localhost:8001/docs`

## 1) System（系统状态）

### 获取系统状态
- `GET /system/status`
- Response
```json
{
  "host": { "cpu": 12.5, "ram": 45.2, "gpu_temp": "N/A" },
  "kali": { "online": true, "cpu": 22.1, "ram": 33.4 }
}
```

## 2) WiFi（C2 扫描/监听/Agent）

### 一键部署 Agent（SSH 上传 + 启动）
- `POST /wifi/agent/deploy`
- Response（示例）
```json
{ "status": "success", "message": "Agent 已成功部署并上线" }
```

### 获取 Agent 网卡列表
- `GET /wifi/interfaces`
- Response（示例）
```json
{
  "interfaces": [
    { "name": "wlan0", "display": "wlan0 [Managed]", "mode": "Managed" },
    { "name": "wlan0mon", "display": "wlan0mon [Monitor]", "mode": "Monitor" }
  ]
}
```

### 触发扫描（后端下发任务，等待 Agent 回传并入库）
- `POST /wifi/scan/start`
- Body
```json
{ "interface": "wlan0" }
```
- Response（示例）
```json
{ "status": "success", "count": 42 }
```

### 获取 WiFi 列表（从数据库读取）
- `GET /wifi/networks`
- Response（示例）
```json
[
  {
    "id": 1,
    "bssid": "AA:BB:CC:DD:EE:FF",
    "ssid": "ExampleWiFi",
    "channel": 6,
    "signal_dbm": -42,
    "encryption": "WPA2",
    "vendor": "Unknown",
    "client_count": 3,
    "last_seen": "2025-12-21T12:34:56.000Z"
  }
]
```

### 启动目标监听（下发 monitor_target 任务）
- `POST /wifi/monitor/start`
- Body
```json
{ "bssid": "AA:BB:CC:DD:EE:FF", "channel": 6, "interface": "wlan0" }
```
- Response（示例）
```json
{ "status": "queued" }
```

### 停止目标监听
- `POST /wifi/monitor/stop`
- Response（示例）
```json
{ "status": "stopped" }
```

### 获取目标客户端列表（从数据库读取）
- `GET /wifi/monitor/clients/{bssid}`
- Response（示例）
```json
[
  {
    "id": 1,
    "network_bssid": "AA:BB:CC:DD:EE:FF",
    "client_mac": "11:22:33:44:55:66",
    "signal_dbm": -51,
    "packet_count": 120,
    "last_seen": "2025-12-21T12:35:10.000Z"
  }
]
```

### Agent 内部接口（由 Kali Agent 调用）
- `POST /wifi/register_agent`
- `GET /wifi/agent/heartbeat`
- `POST /wifi/callback`

### 握手包文件管理（导入/下载）

### 上传抓包文件
- `POST /wifi/handshake/upload`
- Content-Type：`multipart/form-data`
- Form fields
  - `file`：`.cap/.pcap/.pcapng`
  - `bssid`：可选
  - `ssid`：可选
- Response（示例）
```json
{
  "status": "success",
  "filename": "handshake_aabbccddeeff_1734780000.pcap",
  "bssid": "aa:bb:cc:dd:ee:ff",
  "ssid": "ExampleWiFi",
  "size": 123456
}
```

### 列出已上传文件
- `GET /wifi/handshake/list`
- Query
  - `bssid`：可选
- Response（示例）
```json
{
  "items": [
    { "filename": "handshake_aabbccddeeff_1734780000.pcap", "size": 123456, "mtime": 1734780001 }
  ]
}
```

### 下载文件
- `GET /wifi/handshake/download/{filename}`

## 3) AI（DeepSeek）

### AI 聊天
- `POST /ai/chat`
- Body
```json
{ "prompt": "你好", "mode": "general" }
```
- Response（示例）
```json
{ "code": 200, "result": "..." }
```

### WiFi 目标战术分析（返回结构化 JSON）
- `POST /ai/analyze_target`
- Body
```json
{ "ssid": "ExampleWiFi", "bssid": "AA:BB:CC:DD:EE:FF", "encryption": "WPA2" }
```
- Response（示例）
```json
{
  "risk_level": "高危/中危/低危",
  "summary": "简短的目标特征总结（50字以内）",
  "advice": "具体的攻击向量建议（换行显示）",
  "dict_rules": ["建议的字典规则1", "建议的字典规则2"]
}
```
