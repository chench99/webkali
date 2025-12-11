<template>
  <div class="space-y-6">
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-[#1f2937] rounded-xl p-6 border border-gray-700/50 shadow-lg relative overflow-hidden group">
        <div class="absolute right-0 top-0 p-4 opacity-10 group-hover:opacity-20 transition">
          <i class="el-icon-monitor text-9xl"></i>
        </div>
        <h3 class="text-gray-400 text-xs font-bold uppercase tracking-widest mb-4">Windows Host Node</h3>
        <div class="flex gap-8">
          <div>
            <div class="text-4xl font-mono font-bold text-white mb-1">{{ stats.host.cpu }}<span class="text-sm text-gray-500">%</span></div>
            <div class="text-xs text-gray-500">CPU Load</div>
          </div>
          <div>
            <div class="text-4xl font-mono font-bold text-white mb-1">{{ stats.host.ram }}<span class="text-sm text-gray-500">%</span></div>
            <div class="text-xs text-gray-500">RAM Usage</div>
          </div>
        </div>
        <div class="mt-4 w-full bg-gray-700/50 h-1.5 rounded-full overflow-hidden">
          <div class="h-full bg-gradient-to-r from-blue-600 to-blue-400 transition-all duration-1000" :style="`width: ${stats.host.cpu}%`"></div>
        </div>
      </div>

      <div class="bg-[#1f2937] rounded-xl p-6 border border-gray-700/50 shadow-lg relative overflow-hidden group">
        <div class="absolute top-4 right-4 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full" :class="stats.kali.online ? 'bg-green-500 shadow-[0_0_10px_#22c55e]' : 'bg-red-500'"></span>
          <span class="text-xs font-mono" :class="stats.kali.online ? 'text-green-400' : 'text-red-400'">{{ stats.kali.online ? 'ONLINE' : 'DISCONNECTED' }}</span>
        </div>
        <h3 class="text-gray-400 text-xs font-bold uppercase tracking-widest mb-4">Kali Attack Agent</h3>
        <div v-if="stats.kali.online" class="flex gap-8">
          <div>
            <div class="text-4xl font-mono font-bold text-white mb-1">{{ stats.kali.cpu }}<span class="text-sm text-gray-500">%</span></div>
            <div class="text-xs text-gray-500">Agent Load</div>
          </div>
          <div>
            <div class="text-4xl font-mono font-bold text-white mb-1">{{ stats.kali.ram }}<span class="text-sm text-gray-500">%</span></div>
            <div class="text-xs text-gray-500">Mem Usage</div>
          </div>
        </div>
        <div v-else class="h-[52px] flex items-center">
          <button @click="checkConn" class="text-sm bg-red-900/30 hover:bg-red-900/50 text-red-300 border border-red-800/50 px-4 py-2 rounded transition">
            尝试重连 Agent
          </button>
        </div>
        <div class="mt-4 w-full bg-gray-700/50 h-1.5 rounded-full overflow-hidden">
          <div class="h-full bg-gradient-to-r from-green-600 to-green-400 transition-all duration-1000" :style="`width: ${stats.kali.cpu}%`"></div>
        </div>
      </div>
    </div>

    <h3 class="text-lg font-bold text-white mt-8 mb-4">作战模块入口</h3>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      
      <div @click="$router.push('/wifi')" class="bg-[#1f2937] hover:bg-[#2d3748] p-5 rounded-xl border border-gray-700/50 cursor-pointer transition group relative overflow-hidden">
        <div class="absolute right-0 bottom-0 opacity-10 group-hover:opacity-20 group-hover:scale-110 transition-transform duration-500">
          <Connection class="w-24 h-24 text-blue-500" />
        </div>
        <div class="w-10 h-10 rounded-lg bg-blue-900/30 flex items-center justify-center mb-3 group-hover:bg-blue-600 group-hover:shadow-[0_0_15px_rgba(37,99,235,0.5)] transition-all">
          <Connection class="w-5 h-5 text-blue-400 group-hover:text-white" />
        </div>
        <h4 class="text-white font-bold mb-1">无线渗透</h4>
        <p class="text-xs text-gray-500 leading-relaxed">WiFi 扫描、Deauth 攻击。</p>
      </div>

    </div>

    <div class="bg-black rounded-xl border border-gray-700 shadow-2xl flex flex-col h-64 mt-6">
      <div class="bg-[#111827] px-4 py-2 text-[10px] text-gray-500 border-b border-gray-800 flex justify-between font-mono uppercase tracking-widest">
        <span>System Log Stream</span>
        <span class="text-green-500">● Live</span>
      </div>
      <div class="p-4 overflow-y-auto font-mono text-xs flex-1 space-y-1 scrollbar-thin" ref="terminalRef">
        <div v-for="(log, i) in logs" :key="i" class="break-words">
          <span class="text-green-600 mr-2 opacity-70">➜</span>
          <span class="text-gray-400">{{ log }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import api from '@/api'
// ⚠️ 关键修改：只引用存在的图标
import { Connection } from '@element-plus/icons-vue'

const stats = ref({
  host: { cpu: 0, ram: 0 },
  kali: { online: false, cpu: 0, ram: 0 }
})
const logs = ref(['[SYSTEM] Dashboard initialized.'])
const terminalRef = ref(null)

const autoScroll = () => {
  nextTick(() => { if (terminalRef.value) terminalRef.value.scrollTop = terminalRef.value.scrollHeight })
}

const loadStatus = async () => {
  try {
    const res = await api.get('/system/status')
    stats.value = res.data
    if (res.data.kali.online && !stats.value.kali.online) {
      logs.value.push(`[AGENT] Kali connected successfully. CPU: ${res.data.kali.cpu}%`)
      autoScroll()
    }
  } catch (e) {}
}

const checkConn = async () => {
  logs.value.push("[CMD] Retrying connection to Agent...")
  autoScroll()
  await loadStatus()
}

onMounted(() => {
  loadStatus()
  setInterval(loadStatus, 2000)
})
</script>