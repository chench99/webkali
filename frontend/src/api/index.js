import axios from 'axios'

// 创建 axios 实例
const api = axios.create({
  baseURL: '/api/v1', // 配合 vite.config.js 的代理
  timeout: 30000      // 设置超时时间长一点，因为 AI 思考比较慢
})

// 1. 系统接口
export const getSystemStatus = () => api.get('/system/status')
export const testKaliConnection = () => api.post('/system/connect_kali')

// 2. WiFi 扫描接口
// params: { interface: 'wlan0' }
export const startScan = (params) => api.post('/wifi/scan/start', null, { params })
export const stopScan = () => api.post('/wifi/scan/stop')
export const getWifiList = () => api.get('/wifi/networks')
export const getInterfaces = () => api.get('/wifi/interfaces')

// 3. 攻击接口 (Deauth, EvilTwin, AI分析)
// params: { bssid, interface, duration }
export const sendDeauth = (params) => api.post('/wifi/attack/deauth', null, { params })

// data: { ssid, encryption, bssid }
export const analyzeTargetAI = (data) => api.post('/attack/ai/analyze_target', data)

// data: { ssid, interface }
export const startEvilTwin = (data) => api.post('/attack/eviltwin/start', data)

// 4. AI 聊天接口 (新)
// data: { prompt: "你好", mode: "deep" }
export const sendAiChat = (data) => api.post('/ai/chat', data)

export default api