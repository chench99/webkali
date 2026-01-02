<template>
  <div class="min-h-screen bg-[#0b1120] text-gray-300 p-6 flex flex-col font-mono">
    
    <header class="bg-[#1f2937] border border-gray-700 rounded-xl p-4 mb-6 shadow-lg flex justify-between items-center">
      <div class="flex items-center gap-3">
        <span class="text-2xl">🔨</span>
        <h1 class="text-xl font-bold text-white tracking-wider">密码破解中心 (Hashcat)</h1>
      </div>
      <button @click="$router.push('/wifi')" class="px-4 py-2 border border-gray-600 rounded hover:bg-gray-700 text-sm">返回</button>
    </header>

    <div class="flex-1 grid grid-cols-12 gap-6">
      
      <div class="col-span-4 space-y-6">
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-6 shadow-lg">
          <h3 class="text-blue-400 font-bold mb-4 border-b border-gray-700 pb-2">任务配置</h3>
          <div class="space-y-5">
            <div>
              <label class="block text-xs text-gray-500 mb-1.5">目标握手包 (.hc22000)</label>
              <select v-model="selectedHandshake" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500">
                <option value="" disabled>请选择...</option>
                <option v-for="f in handshakes" :key="f" :value="f">{{ f }}</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-gray-500 mb-1.5">密码字典 (.txt)</label>
              <select v-model="selectedWordlist" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500">
                <option value="" disabled>请选择...</option>
                <option v-for="f in wordlists" :key="f" :value="f">{{ f }}</option>
              </select>
            </div>
            <div class="pt-4">
              <button v-if="!isRunning" @click="startCrack" class="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded shadow-lg transition">🚀 开始破解</button>
              <button v-else @click="stopCrack" class="w-full py-3 bg-red-600 hover:bg-red-500 text-white font-bold rounded shadow-lg animate-pulse">⏹ 停止任务</button>
            </div>
          </div>
        </div>
      </div>

      <div class="col-span-8 flex flex-col gap-4">
        
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-4 shadow-lg grid grid-cols-4 gap-4">
          <div class="bg-black/20 p-3 rounded border border-gray-600/30">
            <div class="text-gray-500 text-[10px] uppercase">Status</div>
            <div class="text-lg font-bold" :class="statusColor">{{ crackStatus.state || 'Idle' }}</div>
          </div>
          <div class="bg-black/20 p-3 rounded border border-gray-600/30">
            <div class="text-gray-500 text-[10px] uppercase">Speed</div>
            <div class="text-lg font-bold text-blue-400 font-mono">{{ crackStatus.speed || '0 H/s' }}</div>
          </div>
          <div class="bg-black/20 p-3 rounded border border-gray-600/30">
            <div class="text-gray-500 text-[10px] uppercase">Recovered</div>
            <div class="text-lg font-bold text-green-400 font-mono">{{ crackStatus.recovered || '0/0' }}</div>
          </div>
          <div class="bg-black/20 p-3 rounded border border-gray-600/30">
            <div class="text-gray-500 text-[10px] uppercase">ETA</div>
            <div class="text-lg font-bold text-yellow-400 font-mono">{{ crackStatus.eta || '-' }}</div>
          </div>
          
          <div class="col-span-4 mt-2">
            <div class="flex justify-between text-xs mb-1 text-gray-400">
              <span>Progress</span>
              <span>{{ crackStatus.progress || 0 }}%</span>
            </div>
            <div class="w-full bg-gray-700 h-2 rounded-full overflow-hidden">
              <div class="h-full bg-green-500 transition-all duration-500 ease-out" :style="{ width: (crackStatus.progress || 0) + '%' }"></div>
            </div>
          </div>
        </div>

        <div class="bg-black rounded-xl border border-gray-700 p-4 flex-1 flex flex-col font-mono text-xs shadow-inner relative min-h-[400px]">
          <div class="flex justify-between items-center mb-2 border-b border-gray-800 pb-2">
            <span class="text-gray-500">root@webkali:~/hashcat# console_output</span>
          </div>
          <div class="flex-1 overflow-y-auto space-y-1 custom-scrollbar" ref="logBox">
            <div v-for="(line, i) in logs" :key="i" class="break-all whitespace-pre-wrap">
              <span v-if="line.includes('[SYSTEM]')" class="text-blue-400 font-bold">{{ line }}</span>
              <span v-else-if="line.includes('[AUTO]')" class="text-purple-400">{{ line }}</span>
              <span v-else-if="line.includes('Recovered')" class="text-green-400 font-bold border-b border-green-500">{{ line }}</span>
              <span v-else class="text-gray-300">{{ line }}</span>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const handshakes = ref([])
const wordlists = ref([])
const selectedHandshake = ref('')
const selectedWordlist = ref('')
const isRunning = ref(false)
const logs = ref([])
const crackStatus = ref({}) // 新增状态对象
const logBox = ref(null)
let pollTimer = null

const statusColor = computed(() => {
  const s = crackStatus.value.state || ''
  if (s.includes('Running')) return 'text-green-400 animate-pulse'
  if (s.includes('Exhausted') || s.includes('Quit')) return 'text-red-400'
  if (s.includes('Cracked')) return 'text-green-500'
  return 'text-gray-300'
})

onMounted(async () => {
  await loadFiles()
  if (route.query.hc && handshakes.value.includes(route.query.hc)) {
    selectedHandshake.value = route.query.hc
  } else if (route.query.cap && handshakes.value.includes(route.query.cap)) {
    selectedHandshake.value = route.query.cap
  }
  if (wordlists.value.length > 0) selectedWordlist.value = wordlists.value[0]
  pollTimer = setInterval(fetchLogs, 1000)
})

onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

const loadFiles = async () => {
  try {
    const res1 = await api.get('/crack/files/handshakes')
    handshakes.value = res1.data.files
    const res2 = await api.get('/crack/files/wordlists')
    wordlists.value = res2.data.files
  } catch (e) {}
}

const startCrack = async () => {
  if (!selectedHandshake.value || !selectedWordlist.value) return ElMessage.warning("请选择文件")
  try {
    const res = await api.post('/crack/start', {
      handshake_file: selectedHandshake.value,
      wordlist_file: selectedWordlist.value
    })
    if (res.data.status === 'success') {
      ElMessage.success("任务启动")
      logs.value = []
      isRunning.value = true
    } else {
      ElMessage.error(res.data.message)
    }
  } catch (e) { ElMessage.error(e.message) }
}

const stopCrack = async () => { await api.post('/crack/stop') }

const fetchLogs = async () => {
  try {
    const res = await api.get('/crack/logs')
    isRunning.value = res.data.is_running
    logs.value = res.data.logs
    crackStatus.value = res.data.status || {} // 获取状态
    
    nextTick(() => { if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight })
  } catch (e) {}
}
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
</style>