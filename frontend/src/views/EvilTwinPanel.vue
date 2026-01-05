<template>
  <div class="min-h-screen bg-[#0b1120] text-gray-300 p-6 flex flex-col font-mono">
    
    <header class="bg-[#1f2937] border border-gray-700 rounded-xl p-4 mb-6 shadow-lg flex justify-between items-center">
      <div class="flex items-center gap-3">
        <span class="text-2xl text-purple-400">😈</span>
        <h1 class="text-xl font-bold text-white tracking-wider">Evil Twin 双子攻击配置</h1>
      </div>
      <div class="flex items-center gap-4">
        <span v-if="isRunning" class="text-xs text-green-400 animate-pulse flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-green-500"></span> 攻击运行中
        </span>
        <button @click="$router.push('/')" class="px-4 py-2 border border-gray-600 rounded hover:bg-gray-700 text-sm">返回首页</button>
      </div>
    </header>

    <div class="flex-1 grid grid-cols-12 gap-6">
      
      <div class="col-span-5 space-y-6">
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-6 shadow-lg">
          <h3 class="text-purple-400 font-bold mb-4 border-b border-gray-700 pb-2 flex items-center justify-between">
            <span>⚙️ 攻击参数</span>
            <button @click="refreshData" class="text-xs text-blue-400 hover:text-blue-300 transition">🔄 刷新列表</button>
          </h3>
          
          <div class="space-y-5">
            
            <div class="grid grid-cols-1 gap-4">
              <div>
                <label class="block text-xs text-gray-500 mb-1 flex justify-between">
                  <span>攻击网卡 (Deauth - 负责踢人)</span>
                  <span class="text-[10px] text-red-400">* 必选</span>
                </label>
                <select v-model="form.interface" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none transition">
                  <option value="" disabled>请选择网卡...</option>
                  <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
                    {{ iface.label }}
                  </option>
                </select>
              </div>
              
              <div>
                <label class="block text-xs text-gray-500 mb-1 flex justify-between">
                  <span>AP 网卡 (Hotspot - 负责钓鱼)</span>
                  <span class="text-[10px] text-red-400">* 必选 (需支持 AP 模式)</span>
                </label>
                <select v-model="form.ap_interface" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none transition">
                  <option value="" disabled>请选择网卡...</option>
                  <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
                    {{ iface.label }}
                  </option>
                </select>
                <p v-if="form.interface && form.ap_interface && form.interface === form.ap_interface" class="text-red-500 text-[10px] mt-1 font-bold">
                  ⚠️ 警告: 两张网卡不能相同！
                </p>
              </div>
            </div>

            <div class="border-t border-gray-700 my-2"></div>

            <div>
              <label class="block text-xs text-gray-500 mb-1 flex justify-between">
                <span>选择目标 WiFi (从扫描结果)</span>
                <span v-if="wifiList.length === 0" class="text-[10px] text-yellow-500 cursor-pointer hover:underline" @click="$router.push('/wifi')">列表为空? 去扫描</span>
              </label>
              <select v-model="selectedWifi" @change="onWifiSelected" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-white font-bold focus:border-purple-500 outline-none transition">
                <option :value="null">-- 手动输入 / 自定义 --</option>
                <option v-for="wifi in wifiList" :key="wifi.bssid" :value="wifi">
                  {{ wifi.label }}
                </option>
              </select>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="col-span-2">
                <label class="block text-xs text-gray-500 mb-1">目标 BSSID</label>
                <input v-model="form.bssid" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-400 focus:border-purple-500 outline-none font-mono" placeholder="AA:BB:CC:DD:EE:FF">
              </div>
              <div>
                <label class="block text-xs text-gray-500 mb-1">伪造 SSID</label>
                <input v-model="form.ssid" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:border-purple-500 outline-none">
              </div>
              <div>
                <label class="block text-xs text-gray-500 mb-1">信道</label>
                <input v-model="form.channel" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-400 focus:border-purple-500 outline-none">
              </div>
            </div>

            <div class="border-t border-gray-700 my-2"></div>

            <div>
              <label class="block text-xs text-gray-500 mb-1">选择钓鱼页面模板</label>
              <select v-model="selectedTemplate" @change="onTemplateSelected" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-green-400 focus:border-purple-500 outline-none mb-2 transition">
                <option :value="null">-- 自定义 HTML --</option>
                <option v-for="tpl in templates" :key="tpl.name" :value="tpl">
                  {{ tpl.name }}
                </option>
              </select>
              <textarea v-model="form.template_html" rows="4" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-[10px] text-gray-400 font-mono focus:border-purple-500 outline-none resize-none" placeholder="HTML 代码..."></textarea>
            </div>

            <div class="pt-2">
              <button v-if="!isRunning" @click="startAttack" class="w-full py-3 bg-gradient-to-r from-purple-700 to-purple-900 hover:from-purple-600 hover:to-purple-800 text-white font-bold rounded shadow-lg transition flex justify-center items-center gap-2 transform active:scale-95">
                <span>🚀</span> 启动双子攻击 (无限踢人)
              </button>
              <button v-else @click="stopAttack" class="w-full py-3 bg-red-600 hover:bg-red-500 text-white font-bold rounded shadow-lg animate-pulse flex justify-center items-center gap-2">
                <span>⏹</span> 停止攻击 & 恢复网络
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="col-span-7 flex flex-col gap-6">
        
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-6 shadow-lg flex-1 flex flex-col min-h-[300px]">
          <h3 class="text-green-400 font-bold mb-4 border-b border-gray-700 pb-2 flex justify-between items-center">
            <span class="flex items-center gap-2">🔑 捕获凭证 (Credentials) <span class="text-xs bg-green-900 px-2 py-0.5 rounded text-green-300">{{ capturedCreds.length }}</span></span>
            <span v-if="isRunning" class="text-xs animate-pulse text-green-500 flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-green-500"></span> 监听中...</span>
          </h3>
          
          <div class="flex-1 overflow-y-auto custom-scrollbar bg-black/30 rounded border border-gray-700 p-4">
            <div v-if="capturedCreds.length === 0" class="h-full flex flex-col items-center justify-center text-gray-600 opacity-50">
              <span class="text-5xl mb-4">🕸️</span>
              <p class="text-sm">等待鱼儿上钩...</p>
              <p class="text-xs mt-2">当受害者连接热点并输入密码时显示</p>
            </div>
            <div v-else class="space-y-3">
              <div v-for="(cred, index) in capturedCreds" :key="index" class="bg-green-900/20 border border-green-500/30 p-3 rounded text-green-300 font-mono text-sm break-all shadow-sm flex items-start gap-2">
                <span class="text-green-500 mt-0.5">➜</span>
                <span>{{ cred }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="bg-black rounded-xl border border-gray-700 p-4 h-64 flex flex-col font-mono text-xs shadow-inner relative">
          <div class="text-gray-500 border-b border-gray-800 pb-2 mb-2 flex justify-between uppercase tracking-widest text-[10px]">
            <span>System & Attack Logs</span>
            <span v-if="isRunning" class="text-purple-400">LIVE</span>
          </div>
          <div class="flex-1 overflow-y-auto space-y-1 custom-scrollbar" ref="logRef">
            <div v-for="(log, i) in logs" :key="i" class="break-words font-mono">
              <span v-if="log.includes('[SYSTEM]')" class="text-blue-400 font-bold">{{ log }}</span>
              <span v-else-if="log.includes('Sending')" class="text-red-400/80">{{ log }}</span>
              <span v-else-if="log.includes('Hostapd')" class="text-purple-400">{{ log }}</span>
              <span v-else class="text-gray-500">{{ log }}</span>
            </div>
            <div v-if="logs.length === 0" class="text-gray-700 italic text-center mt-10">Waiting for logs...</div>
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
const logs = ref(['[SYSTEM] Ready to configure Evil Twin attack.'])
const capturedCreds = ref([])
const logRef = ref(null)
let pollTimer = null

// 数据源
const interfaces = ref([]) 
const wifiList = ref([])   
const templates = ref([])  

// 选中的对象
const selectedWifi = ref(null)
const selectedTemplate = ref(null)

// 表单
const form = ref({
  interface: '',      // 攻击卡
  ap_interface: '',   // AP卡
  bssid: '',
  ssid: '',
  channel: '6',
  duration: 300,      // 此参数在 Evil Twin 模式下会被后端忽略强制为0(无限)
  template_html: ''
})

const addLog = (msg) => {
  if (logs.value.length > 200) logs.value.shift() // 限制日志长度
  logs.value.push(msg)
  nextTick(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight })
}

// 刷新所有数据
const refreshData = async () => {
  try {
    addLog("[SYSTEM] Fetching system info...")
    
    // 1. 获取网卡
    const res1 = await api.get('/system/interfaces')
    interfaces.value = res1.data.data || []

    // 2. 获取扫描结果
    const res2 = await api.get('/wifi/scan/results')
    wifiList.value = res2.data.data || []

    // 3. 获取模板
    const res3 = await api.get('/attack/eviltwin/templates')
    templates.value = res3.data.data || []
    
    // 默认选中第一个模板
    if(templates.value.length > 0 && !form.value.template_html) {
      selectedTemplate.value = templates.value[0]
      form.value.template_html = templates.value[0].content
    }
    
    ElMessage.success("数据已刷新")
  } catch (e) {
    ElMessage.error("数据加载失败: " + e.message)
    addLog(`[ERROR] ${e.message}`)
  }
}

// 联动：选中 WiFi 后自动填充
const onWifiSelected = () => {
  if (selectedWifi.value) {
    form.value.bssid = selectedWifi.value.bssid
    form.value.ssid = selectedWifi.value.ssid
    form.value.channel = selectedWifi.value.channel
  }
}

// 联动：选中模板后填充
const onTemplateSelected = () => {
  if (selectedTemplate.value) {
    form.value.template_html = selectedTemplate.value.content
  }
}

const startAttack = async () => {
  if (!form.value.interface || !form.value.ap_interface) return ElMessage.warning("请选择两张网卡")
  if (form.value.interface === form.value.ap_interface) return ElMessage.error("两张网卡不能相同")
  if (!form.value.bssid) return ElMessage.warning("请选择或填写目标 BSSID")

  addLog(`[SYSTEM] Launching Evil Twin...`)
  addLog(`[CONFIG] Deauth: ${form.value.interface} | AP: ${form.value.ap_interface} | Target: ${form.value.ssid}`)
  
  try {
    const res = await api.post('/attack/eviltwin/start', form.value)
    if (res.data.status === 'started') {
      isRunning.value = true
      addLog(`[SYSTEM] 攻击已启动！请观察下方 Deauth 日志...`)
      ElMessage.success("攻击已启动")
      // 启动轮询
      pollTimer = setInterval(fetchDataLoop, 2000)
    }
  } catch (e) {
    addLog(`[ERROR] ${e.message}`)
    ElMessage.error(e.message)
  }
}

const stopAttack = async () => {
  try {
    await api.post('/attack/eviltwin/stop')
    isRunning.value = false
    addLog("[SYSTEM] 攻击已停止。")
    if (pollTimer) clearInterval(pollTimer)
  } catch (e) {}
}

// 轮询数据 (日志 + 密码)
const fetchDataLoop = async () => {
  if (!isRunning.value) return

  // 1. 获取密码
  try {
    const res = await api.get('/attack/eviltwin/credentials')
    if (res.data.status === 'success' && res.data.data) {
      res.data.data.forEach(c => {
        if (!capturedCreds.value.includes(c)) {
          capturedCreds.value.push(c)
          ElMessage.success("🔥 捕获到密码！")
          // 播放提示音或高亮
        }
      })
    }
  } catch (e) {}

  // 2. 获取日志 (重要：为了看踢人效果)
  try {
    const res = await api.get('/attack/eviltwin/logs')
    if (res.data.status === 'success' && res.data.logs) {
      const newLogs = res.data.logs
      // 过滤重复日志，只显示最新的动态
      newLogs.forEach(log => {
        // 只添加最后一条日志不一样的，防止刷屏太快
        if (logs.value[logs.value.length - 1] !== log) {
           addLog(log)
        }
      })
    }
  } catch (e) {}
}

onMounted(() => {
  refreshData()
})

onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-track { background: #111827; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #374151; border-radius: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #4b5563; }
</style>