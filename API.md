### 📂 文档 3：接口规范文档 (API.md)
**存放位置：** `docs/API.md`
**用途：** 前后端对接的标准。虽然 FastAPI 自带 Swagger，但这份文档用于宏观规划。

```markdown
# 🔌 API 接口文档 (v1)

> **实时交互文档:** 启动后端后访问 `http://localhost:8000/docs` 查看 Swagger UI。

## 1. System (系统管理)

### 获取系统状态
`GET /api/v1/system/monitor`
* **Response:**
  ```json
  {
    "host": { "cpu_usage": 12.5, "ram_usage": 45.2, "gpu_temp": 55 },
    "kali": { "status": "online", "latency": "5ms" },
    "tasks": { "running": 2, "queued": 0 }
  }
```
sk-37294e78cfa84cc4be7a249b0b7a85bd