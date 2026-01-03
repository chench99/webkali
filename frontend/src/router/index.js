import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import WiFiPanel from '../views/WiFiPanel.vue'
import AIAssistant from '../views/AIAssistant.vue'
import AttackDetail from '../views/AttackDetail.vue'
import CrackPanel from '../views/CrackPanel.vue'
import EvilTwinPanel from '../views/EvilTwinPanel.vue' // <--- 1. 引入新页面

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/wifi', name: 'WiFiPanel', component: WiFiPanel },
  { path: '/ai', name: 'AIAssistant', component: AIAssistant },
  { path: '/wifi/attack/:bssid', name: 'AttackDetail', component: AttackDetail },
  { path: '/crack', name: 'CrackPanel', component: CrackPanel },
  { path: '/eviltwin', name: 'EvilTwinPanel', component: EvilTwinPanel } // <--- 2. 添加路由
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router