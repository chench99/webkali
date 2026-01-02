import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import WiFiPanel from '../views/WiFiPanel.vue'
import AIAssistant from '../views/AIAssistant.vue'
import AttackDetail from '../views/AttackDetail.vue'
import CrackPanel from '../views/CrackPanel.vue' // [新增]

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/wifi', name: 'WiFiPanel', component: WiFiPanel },
  { path: '/ai', name: 'AIAssistant', component: AIAssistant },
  { path: '/wifi/attack/:bssid', name: 'AttackDetail', component: AttackDetail },
  { path: '/crack', name: 'CrackPanel', component: CrackPanel } // [新增]
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router