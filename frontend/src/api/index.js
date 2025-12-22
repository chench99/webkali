import axios from 'axios'

// 创建 axios 实例
const api = axios.create({
  baseURL: '/api/v1', // 配合 vite.config.js 的代理
  // 【关键修改】将超时时间从 30000 改为 90000 (90秒)
  // 因为握手包捕获通常需要 45-60 秒，AI 分析也可能很慢
  timeout: 90000      
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
// 注意：这里我们修正过路径，但在 index.js 里也要确保用的是通用请求方式
// 下面这些导出函数虽然被 AttackDetail.vue 用 api.post 直接替代了，但保留着也没错
export const analyzeTargetAI = (data) => api.post('/ai/analyze_target', data)

// data: { ssid, interface }
export const startEvilTwin = (data) => api.post('/attack/eviltwin/start', data)

// 4. AI 聊天接口 (新)
// data: { prompt: "你好", mode: "deep" }
export const sendAiChat = (data) => api.post('/ai/chat', data)

export default api