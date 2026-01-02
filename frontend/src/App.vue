<template>
  <div class="flex h-screen bg-[#0b1120] text-gray-300 font-sans overflow-hidden">
    <aside class="w-64 bg-[#111827] border-r border-gray-800 flex flex-col shadow-2xl z-20">
      <div class="h-16 flex items-center px-6 border-b border-gray-800 bg-[#0f1623]">
        <div class="w-8 h-8 bg-gradient-to-tr from-green-500 to-blue-600 rounded-lg mr-3 flex items-center justify-center shadow-lg">
          <span class="text-white font-bold text-lg">K</span>
        </div>
        <span class="text-xl font-bold tracking-wider text-gray-100">KALI <span class="text-green-500">C2</span></span>
      </div>

      <nav class="flex-1 py-6 space-y-1 overflow-y-auto">
        <router-link 
          v-for="item in menuItems" 
          :key="item.path" 
          :to="item.path"
          class="flex items-center px-6 py-3 text-sm font-medium transition-all duration-200 border-l-4 border-transparent hover:bg-gray-800/50 hover:text-white group"
          active-class="bg-gray-800/80 border-green-500 text-white shadow-inner"
        >
          <component :is="item.icon" class="w-5 h-5 mr-3 text-gray-500 group-hover:text-green-400 transition-colors" />
          {{ item.name }}
        </router-link>
      </nav>

      <div class="p-4 border-t border-gray-800 bg-[#0f1623]">
        <div class="flex items-center">
          <div class="w-2 h-2 rounded-full bg-green-500 animate-pulse mr-2"></div>
          <span class="text-xs text-gray-500">System Stable</span>
        </div>
      </div>
    </aside>

    <main class="flex-1 flex flex-col relative overflow-hidden">
      <header class="h-16 bg-[#111827]/80 backdrop-blur-md border-b border-gray-800 flex items-center justify-between px-8 z-10">
        <h2 class="text-lg font-medium text-white">{{ currentRouteName }}</h2>
        <div class="flex items-center gap-4">
          <span class="text-xs px-2 py-1 bg-blue-900/30 text-blue-400 rounded border border-blue-900/50">Admin Access</span>
          <div class="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center border border-gray-600">
            <UserIcon class="w-4 h-4 text-gray-300" />
          </div>
        </div>
      </header>

      <div class="flex-1 overflow-y-auto p-8 scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
// 引入图标 (新增 Unlock)
import { 
  Monitor, 
  Connection, 
  ChatLineSquare, 
  User as UserIcon,
  Unlock // [新增] 破解图标
} from '@element-plus/icons-vue'

const route = useRoute()

// 计算当前页面标题
const currentRouteName = computed(() => {
  const map = {
    'Dashboard': '指挥控制中心',
    'WiFiPanel': '无线渗透控制台',
    'AttackDetail': '单兵作战终端',
    'CrackPanel': '密码破解中心', // [新增]
    'AIAssistant': 'AI 战术参谋部'
  }
  return map[route.name] || 'Kali C2 Platform'
})

// === 菜单配置 ===
const menuItems = [
  { name: '仪表盘', path: '/', icon: Monitor },
  { name: '无线渗透', path: '/wifi', icon: Connection },
  { name: '密码破解', path: '/crack', icon: Unlock }, // [新增] 侧边栏入口
  { name: 'AI 参谋部', path: '/ai', icon: ChatLineSquare },
]
</script>

<style>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #374151; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #4b5563; }
</style>