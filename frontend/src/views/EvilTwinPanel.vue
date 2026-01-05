<template>
  <div class="min-h-screen bg-[#0b1120] text-gray-300 p-6 flex flex-col font-mono">
    
    <header class="bg-[#1f2937] border border-gray-700 rounded-xl p-4 mb-6 shadow-lg flex justify-between items-center">
      <div class="flex items-center gap-3">
        <span class="text-2xl text-purple-400">😈</span>
        <h1 class="text-xl font-bold text-white tracking-wider">Evil Twin Pro <span class="text-xs text-gray-400 ml-2">5G Ready</span></h1>
      </div>
      <button @click="$router.push('/')" class="px-4 py-2 border border-gray-600 rounded hover:bg-gray-700 text-sm">返回</button>
    </header>

    <div class="flex-1 grid grid-cols-12 gap-6">
      
      <div class="col-span-5 space-y-6">
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-6 shadow-lg">
          <h3 class="text-purple-400 font-bold mb-4 border-b border-gray-700 pb-2 flex justify-between">
            <span>⚙️ 攻击配置</span>
            <button @click="refresh" class="text-xs text-blue-400 hover:text-blue-300">🔄 刷新</button>
          </h3>
          
          <div class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="text-xs text-gray-500 block mb-1">攻击网卡 (Deauth)</label>
                <select v-model="form.interface" class="w-full bg-black/30 border border-gray-600 rounded px-2 py-2 text-sm">
                  <option v-for="i in interfaces" :key="i.name" :value="i.name">{{ i.label }}</option>
                </select>
              </div>
              <div>
                <label class="text-xs text-gray-500 block mb-1">AP 网卡 (Hotspot)</label>
                <select v-model="form.ap_interface" class="w-full bg-black/30 border border-gray-600 rounded px-2 py-2 text-sm">
                  <option v-for="i in interfaces" :key="i.name" :value="i.name">{{ i.label }}</option>
                </select>
              </div>
            </div>

            <div>
              <label class="text-xs text-gray-500 block mb-1">选择目标 (扫描结果)</label>
              <select v-model="selectedWifi" @change="onWifiSelected" class="w-full bg-black/30 border border-gray-600 rounded px-2 py-2 text-sm font-bold text-white">
                <option :value="null">-- 手动设置 --</option>
                <option v-for="w in wifiList" :key="w.bssid" :value="w">{{ w.label }}</option>
              </select>
            </div>

            <div class="bg-black/20 p-3 rounded border border-gray-700">
              <label class="text-xs text-purple-400 block mb-2 font-bold">AP 发射参数</label>
              
              <div class="flex gap-4 mb-3">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="radio" v-model="form.band" value="2.4g" class="accent-purple-500">
                  <span class="text-sm">2.4 GHz</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="radio" v-model="form.band" value="5g" class="accent-purple-500">
                  <span class="text-sm">5 GHz (高速)</span>
                </label>
              </div>

              <div class="grid grid-cols-2 gap-2">
                <input v-model="form.bssid" placeholder="目标 BSSID" class="bg-black/30 border border-gray-600 rounded px-2 py-1 text-xs">
                <input v-model="form.ssid" placeholder="伪造 SSID" class="bg-black/30 border border-gray-600 rounded px-2 py-1 text-xs text-white font-bold">
                
                <div class="col-span-2 flex gap-2">
                  <input v-model="form.channel" placeholder="信道 (如 1, 6, 40)" class="flex-1 bg-black/30 border border-gray-600 rounded px-2 py-1 text-xs text-yellow-400 font-mono">
                  <button @click="form.channel='0'" class="px-2 bg-blue-900/50 text-blue-300 text-[10px] border border-blue-800 rounded hover:bg-blue-800" title="Hostapd ACS 自动选择最优信道">Auto (ACS)</button>
                </div>
              </div>
            </div>

            <div>
              <label class="text-xs text-gray-500 block mb-1">钓鱼模版</label>
              <select v-model="selectedTemplate" @change="onTplSelected" class="w-full bg-black/30 border border-gray-600 rounded px-2 py-2 text-sm mb-2">
                <option :value="null">-- 自定义 --</option>
                <option v-for="t in templates" :key="t.name" :value="t">{{ t.name }}</option>
              </select>
              <textarea v-model="form.template_html" rows="3" class="w-full bg-black/30 border border-gray-600 rounded p-2 text-[10px] font-mono"></textarea>
            </div>

            <button v-if="!isRunning" @click="start" class="w-full py-3 bg-purple-700 hover:bg-purple-600 text-white font-bold rounded shadow-lg transition transform active:scale-95">
              🚀 启动双子星 ({{ form.band.toUpperCase() }})
            </button>
            <button v-else @click="stop" class="w-full py-3 bg-red-600 hover:bg-red-500 text-white font-bold rounded shadow-lg animate-pulse">
              ⏹ 停止攻击
            </button>
          </div>
        </div>
      </div>

      <div class="col-span-7 flex flex-col gap-6">
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-6 shadow-lg flex-1">
          <h3 class="text-green-400 font-bold mb-4 border-b border-gray-700 pb-2 flex justify-between">
            <span>🔑 捕获凭证</span>
            <span v-if="isRunning" class="text-xs text-green-500 animate-pulse">● Monitoring</span>
          </h3>
          <div class="h-40 overflow-y-auto bg-black/30 rounded p-4 space-y-2">
             <div v-for="c in creds" :key="c" class="text-green-300 font-mono text-sm border-b border-green-900/30 pb-1 flex gap-2">
               <span class="text-green-500">➜</span> {{ c }}
             </div>
             <div v-if="creds.length==0" class="text-gray-600 text-center mt-8">暂无数据...</div>
          </div>
        </div>

        <div class="bg-black rounded-xl border border-gray-700 p-4 h-64 flex flex-col font-mono text-xs shadow-inner">
          <div class="text-gray-500 border-b border-gray-800 pb-1 mb-1 flex justify-between text-[10px] uppercase">
            <span>Real-time Logs</span>
            <span class="text-gray-600">AP & Deauth Stream</span>
          </div>
          <div class="flex-1 overflow-y-auto space-y-1" ref="logRef">
            <div v-for="(l, i) in logs" :key="i" class="break-words">
              <span v-if="l.includes('Attack')" class="text-red-400 font-bold">{{ l }}</span>
              <span v-else-if="l.includes('Hostapd')" class="text-blue-400">{{ l }}</span>
              <span v-else-if="l.includes('Search')" class="text-yellow-500">{{ l }}</span>
              <span v-else class="text-gray-500">{{ l }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

const isRunning = ref(false)
const logs = ref(['[SYSTEM] Ready.'])
const creds = ref([])
const logRef = ref(null)
let timer = null

const interfaces = ref([])
const wifiList = ref([])
const templates = ref([])
const selectedWifi = ref(null)
const selectedTemplate = ref(null)

const form = ref({
  interface: '', ap_interface: '', bssid: '', ssid: '', 
  channel: '6', band: '2.4g', template_html: '', duration: 0
})

const addLog = (msg) => {
  if (logs.value.length > 100) logs.value.shift()
  logs.value.push(msg)
  nextTick(() => logRef.value && (logRef.value.scrollTop = logRef.value.scrollHeight))
}

const refresh = async () => {
  try {
    const [r1, r2, r3] = await Promise.all([
      api.get('/system/interfaces'), api.get('/wifi/scan/results'), api.get('/attack/eviltwin/templates')
    ])
    interfaces.value = r1.data.data || []
    wifiList.value = r2.data.data || []
    templates.value = r3.data.data || []
    if (templates.value.length) {
      selectedTemplate.value = templates.value[0]
      form.value.template_html = templates.value[0].content
    }
  } catch (e) { ElMessage.error("刷新失败") }
}

const onWifiSelected = () => {
  if (selectedWifi.value) {
    const w = selectedWifi.value
    form.value.bssid = w.bssid
    form.value.ssid = w.ssid
    form.value.channel = w.channel
    // 智能判断频段 (信道 > 14 默认为 5G)
    if (parseInt(w.channel) > 14) {
      form.value.band = '5g'
      ElMessage.info("检测到 5G WiFi，已自动切换频段")
    } else {
      form.value.band = '2.4g'
    }
  }
}

const onTplSelected = () => { if(selectedTemplate.value) form.value.template_html = selectedTemplate.value.content }

const start = async () => {
  if (!form.value.interface || !form.value.ap_interface) return ElMessage.warning("请选择网卡")
  addLog(`[SYSTEM] 正在启动... Band: ${form.value.band} | Channel: ${form.value.channel}`)
  
  try {
    const res = await api.post('/attack/eviltwin/start', form.value)
    if (res.data.status === 'started') {
      isRunning.value = true
      timer = setInterval(poll, 2000)
    }
  } catch (e) { addLog(`[ERROR] ${e.message}`) }
}

const stop = async () => {
  await api.post('/attack/eviltwin/stop')
  isRunning.value = false
  clearInterval(timer)
  addLog("[SYSTEM] 攻击已停止")
}

const poll = async () => {
  try {
    const c = await api.get('/attack/eviltwin/credentials')
    if (c.data.data) c.data.data.forEach(x => { if (!creds.value.includes(x)) creds.value.push(x) })
    
    const l = await api.get('/attack/eviltwin/logs')
    if (l.data.logs) l.data.logs.forEach(x => { if (logs.value[logs.value.length-1] !== x) addLog(x) })
  } catch(e) {}
}

onMounted(refresh)
onUnmounted(() => clearInterval(timer))
</script>