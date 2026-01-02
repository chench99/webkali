import axios from 'axios'

// 创建 axios 实例
const api = axios.create({
  baseURL: '/api/v1', 
  // ⚠️ 关键修复：将超时时间从 30s 改为 120s (2分钟)
  // 因为握手包捕获通常需要 30-60秒，加上 SSH 开销，30s 绝对不够
  timeout: 120000      
})

// === 1. 系统与基础 ===
export const getSystemStatus = () => api.get('/system/status')

// === 2. WiFi 扫描与管理 ===
export const startScan = (data) => api.post('/wifi/scan/start', data)
export const getWifiList = () => api.get('/wifi/networks')
export const getInterfaces = () => api.get('/wifi/interfaces')
export const deployAgent = () => api.post('/wifi/agent/deploy')

// === 3. 监听模块 ===
export const startMonitor = (data) => api.post('/wifi/monitor/start', data)
export const stopMonitor = () => api.post('/wifi/monitor/stop')
export const getMonitorClients = (bssid) => api.get(`/wifi/monitor/clients/${bssid}`)
export const startDeepScan = () => api.post('/wifi/monitor/deep')
export const getDeepResults = () => api.get('/wifi/monitor/deep_results')

// === 4. 攻击模块 ===
export const sendDeauth = (data) => api.post('/attack/deauth', data)
// 这个接口响应最慢，最容易超时
export const captureHandshake = (data) => api.post('/attack/handshake', data)
export const startEvilTwin = (data) => api.post('/attack/eviltwin/start', data)
export const analyzeTargetAI = (data) => api.post('/attack/ai/analyze_target', data)

// === 5. 默认导出 ===
export default api