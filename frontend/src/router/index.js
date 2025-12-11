import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import WiFiPanel from '../views/WiFiPanel.vue'
// 1. 引入新页面
import AttackDetail from '../views/AttackDetail.vue'
import AIAssistant from '../views/AIAssistant.vue'

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/wifi', name: 'WiFiPanel', component: WiFiPanel },
  // 2. 确保这个路由存在！
  { path: '/wifi/attack/:bssid', name: 'AttackDetail', component: AttackDetail },
  { path: '/ai', name: 'AIAssistant', component: AIAssistant }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router