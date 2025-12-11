<template>
  <div class="min-h-screen bg-gray-900 text-white p-6">
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-2xl font-bold text-green-500">📡 无线渗透控制台</h1>
      <div class="flex gap-4">
        <select v-model="selectedIface" class="bg-gray-800 border border-gray-600 rounded px-3 py-1 text-sm min-w-[240px] text-gray-300 outline-none">
          <option v-for="iface in interfaceList" :key="iface.name" :value="iface.name">
            {{ iface.type === 'usb' ? '🔌' : '💻' }} {{ iface.label }}
          </option>
        </select>
        
        <button 
          @click="toggleScan" 
          class="px-4 py-2 rounded font-bold transition flex items-center gap-2 shadow-lg"
          :class="isScanning ? 'bg-red-600 hover:bg-red-700' : 'bg-green-600 hover:bg-green-700'">
          <span v-if="isScanning" class="animate-pulse w-2 h-2 bg-white rounded-full"></span>
          {{ isScanning ? '停止扫描' : '开始扫描' }}
        </button>
      </div>
    </div>

    <div class="bg-gray-800 rounded-lg shadow-xl overflow-hidden border border-gray-700">
      <table class="w-full text-left border-collapse">
        <thead class="bg-[#111827] text-gray-400 text-xs uppercase tracking-wider">
          <tr>
            <th class="p-4">ESSID</th>
            <th class="p-4">BSSID</th>
            <th class="p-4">信道</th>
            <th class="p-4">加密</th>
            <th class="p-4">信号</th>
            <th class="p-4">情报</th>
            <th class="p-4 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="text-sm divide-y divide-gray-700">
          <tr v-for="net in networks" :key="net.bssid" class="hover:bg-gray-700/50 transition group">
            <td class="p-4 font-bold text-white flex items-center gap-2">
              <span class="w-2 h-2 rounded-full" :class="parseInt(net.signal) > -60 ? 'bg-green-500' : 'bg-yellow-500'"></span>
              {{ net.ssid || '<隐藏网络>' }}
            </td>
            <td class="p-4 font-mono text-gray-400">{{ net.bssid }}</td>
            <td class="p-4 text-gray-300">{{ net.channel }}</td>
            <td class="p-4">
              <span class="px-2 py-1 rounded text-xs border" 
                :class="net.encryption.includes('WPA') ? 'bg-green-900/30 border-green-800 text-green-400' : 'bg-red-900/30 border-red-800 text-red-400'">
                {{ net.encryption }}
              </span>
            </td>
            <td class="p-4 text-gray-400">{{ net.signal }}</td>
            
            <td class="p-4">
               <span v-if="net.clients > 0" class="text-green-400 font-bold flex items-center gap-1">
                 👥 {{ net.clients }}
               </span>
               <span v-else class="text-gray-600">-</span>
            </td>

            <td class="p-4 text-right">
              <button 
                @click="goToAttackPanel(net)" 
                class="bg-blue-600 hover:bg-blue-500 text-white px-3 py-1.5 rounded text-xs transition shadow-lg flex items-center gap-1 ml-auto">
                <span>⚡ 进入作战</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router' // 引入路由钩子
import api from '@/api'

const router = useRouter() // 获取路由实例
const networks = ref([])
const isScanning = ref(false)
const selectedIface = ref('')
const interfaceList = ref([])
let pollInterval = null

// === 跳转到攻击详情页 ===
const goToAttackPanel = (net) => {
  // 停止扫描，防止占用网卡
  if (isScanning.value) {
    toggleScan()
  }
  // 跳转路由：/wifi/attack/AA:BB:CC:11:22:33
  router.push(`/wifi/attack/${net.bssid}`)
}

const loadInterfaces = async () => {
  try {
    const res = await api.get('/wifi/interfaces')
    interfaceList.value = res.data
    const usbIface = res.data.find(i => i.type === 'usb')
    selectedIface.value = usbIface ? usbIface.name : (res.data[0]?.name || 'wlan0')
  } catch (e) {
    interfaceList.value = [{ name: 'wlan0', label: 'wlan0 (Default)', type: 'pci' }]
    selectedIface.value = 'wlan0'
  }
}

const toggleScan = async () => {
  if (isScanning.value) {
    try { await api.post('/wifi/scan/stop') } catch(e) {}
    isScanning.value = false
    clearInterval(pollInterval)
  } else {
    try {
      await api.post('/wifi/scan/start', null, { params: { interface: selectedIface.value } })
      isScanning.value = true
      pollInterval = setInterval(fetchNetworks, 2000)
    } catch (e) {
      alert("启动失败: " + e.message)
      isScanning.value = false
    }
  }
}

const fetchNetworks = async () => {
  try {
    const res = await api.get('/wifi/networks')
    if (res.data) {
      // 简单排序：有客户端的排前面，信号强的排前面
      networks.value = res.data.sort((a, b) => {
        if ((b.clients || 0) !== (a.clients || 0)) return (b.clients || 0) - (a.clients || 0)
        return parseInt(b.signal) - parseInt(a.signal)
      })
    }
  } catch (e) {}
}

onMounted(() => { loadInterfaces() })
onUnmounted(() => { clearInterval(pollInterval) })
</script>