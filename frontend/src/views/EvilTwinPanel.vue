<template>
  <div class="min-h-screen bg-[#0b1120] text-gray-300 p-6 flex flex-col font-mono">
    
    <header class="bg-[#1f2937] border border-gray-700 rounded-xl p-4 mb-6 shadow-lg flex justify-between items-center">
      <div class="flex items-center gap-3">
        <span class="text-2xl text-purple-400">😈</span>
        <h1 class="text-xl font-bold text-white tracking-wider">Evil Twin 双子攻击配置</h1>
      </div>
      <button @click="$router.push('/')" class="px-4 py-2 border border-gray-600 rounded hover:bg-gray-700 text-sm">返回首页</button>
    </header>

    <div class="flex-1 grid grid-cols-12 gap-6">
      
      <div class="col-span-5 space-y-6">
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-6 shadow-lg">
          <h3 class="text-purple-400 font-bold mb-4 border-b border-gray-700 pb-2 flex items-center justify-between">
            <span>⚙️ 攻击参数</span>
            <button @click="refreshData" class="text-xs text-blue-400 hover:text-blue-300">🔄 刷新列表</button>
          </h3>
          
          <div class="space-y-5">
            
            <div class="grid grid-cols-1 gap-4">
              <div>
                <label class="block text-xs text-gray-500 mb-1 flex justify-between">
                  <span>攻击网卡 (Deauth - 负责踢人)</span>
                  <span class="text-[10px] text-red-400">* 必选</span>
                </label>
                <select v-model="form.interface" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none">
                  <option value="" disabled>请选择网卡...</option>
                  <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
                    {{ iface.label }}
                  </option>
                </select>
              </div>
              
              <div>
                <label class="block text-xs text-gray-500 mb-1 flex justify-between">
                  <span>AP 网卡 (Hotspot - 负责钓鱼)</span>
                  <span class="text-[10px] text-red-400">* 必选 (需与攻击网卡不同)</span>
                </label>
                <select v-model="form.ap_interface" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none">
                  <option value="" disabled>请选择网卡...</option>
                  <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
                    {{ iface.label }}
                  </option>
                </select>
                <p v-if="form.interface && form.ap_interface && form.interface === form.ap_interface" class="text-red-500 text-[10px] mt-1">
                  ⚠️ 警告: 攻击网卡和 AP 网卡不能相同！
                </p>
              </div>
            </div>

            <div class="border-t border-gray-700 my-2"></div>

            <div>
              <label class="block text-xs text-gray-500 mb-1 flex justify-between">
                <span>选择目标 WiFi (从扫描结果)</span>
                <span v-if="wifiList.length === 0" class="text-[10px] text-yellow-500">列表为空? 请先去无线扫描</span>
              </label>
              <select v-model="selectedWifi" @change="onWifiSelected" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-white font-bold focus:border-purple-500 outline-none">
                <option :value="null">-- 手动输入 / 自定义 --</option>
                <option v-for="wifi in wifiList" :key="wifi.bssid" :value="wifi">
                  {{ wifi.label }}
                </option>
              </select>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="col-span-2">
                <label class="block text-xs text-gray-500 mb-1">目标 BSSID</label>
                <input v-model="form.bssid" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-400 focus:border-purple-500 outline-none font-mono">
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
              <select v-model="selectedTemplate" @change="onTemplateSelected" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-green-400 focus:border-purple-500 outline-none mb-2">
                <option :value="null">-- 自定义 HTML --</option>
                <option v-for="tpl in templates" :key="tpl.name" :value="tpl">
                  {{ tpl.name }}
                </option>
              </select>
              <textarea v-model="form.template_html" rows="4" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-[10px] text-gray-400 font-mono focus:border-purple-500 outline-none resize-none" placeholder="HTML 代码..."></textarea>
            </div>

            <div class="pt-2">
              <button v-if="!isRunning" @click="startAttack" class="w-full py-3 bg-purple-700 hover:bg-purple-600 text-white font-bold rounded shadow-lg transition flex justify-center items-center gap-2">
                <span>🚀</span> 启动双子攻击
              </button>
              <button v-else @click="stopAttack" class="w-full py-3 bg-red-600 hover:bg-red-500 text-white font-bold rounded shadow-lg animate-pulse flex justify-center items-center gap-2">
                <span>⏹</span> 停止攻击
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="col-span-7 flex flex-col gap-6">
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-6 shadow-lg flex-1 flex flex-col min-h-[300px]">
          <h3 class="text-green-400 font-bold mb-4 border-b border-gray-700 pb-2 flex justify-between items-center">
            <span>🔑 捕获凭证 (Credentials)</span>
            <span v-if="isRunning" class="text-xs animate-pulse text-green-500">● 监听中...</span>
          </h3>
          <div class="flex-1 overflow-y-auto custom-scrollbar bg-black/30 rounded border border-gray-700 p-4">
            <div v-if="capturedCreds.length === 0" class="h-full flex flex-col items-center justify-center text-gray-600">
              <span class="text-4xl mb-2">🕸️</span>
              <p>等待鱼儿上钩...</p>
            </div>
            <div v-else class="space-y-2">
              <div v-for="(cred, index) in capturedCreds" :key="index" class="bg-green-900/20 border border-green-500/30 p-3 rounded text-green-300 font-mono text-sm break-all">
                <span class="text-green-500 font-bold mr-2">[捕获]</span> {{ cred }}
              </div>
            </div>
          </div>
        </div>

        <div class="bg-black rounded-xl border border-gray-700 p-4 h-48 flex flex-col font-mono text-xs shadow-inner">
          <div class="text-gray-500 border-b border-gray-800 pb-1 mb-1">运行日志</div>
          <div class="flex-1 overflow-y-auto space-y-1 custom-scrollbar" ref="logRef">
            <div v-for="(log, i) in logs" :key="i" class="text-gray-400">
              <span class="text-purple-500">➜</span> {{ log }}
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
const logs = ref(['[SYSTEM] Initializing...'])
const capturedCreds = ref([])
const logRef = ref(null)
let pollTimer = null

// 数据源
const interfaces = ref([]) // 网卡列表
const wifiList = ref([])   // WiFi 列表
const templates = ref([])  // 模板列表

// 选中的对象
const selectedWifi = ref(null)
const selectedTemplate = ref(null)

// 表单
const form = ref({
  interface: '',
  ap_interface: '',
  bssid: '',
  ssid: '',
  channel: '6',
  duration: 300,
  template_html: ''
})

const addLog = (msg) => {
  logs.value.push(msg)
  nextTick(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight })
}

// 核心：刷新所有数据
const refreshData = async () => {
  try {
    addLog("[CMD] Fetching system info...")
    
    // 1. 获取网卡
    const res1 = await api.get('/system/interfaces')
    interfaces.value = res1.data.data || []
    if(interfaces.value.length > 0) addLog(`[INFO] Found ${interfaces.value.length} network interfaces`)

    // 2. 获取扫描结果
    const res2 = await api.get('/wifi/scan/results')
    wifiList.value = res2.data.data || []
    if(wifiList.value.length > 0) addLog(`[INFO] Loaded ${wifiList.value.length} scanned networks`)

    // 3. 获取模板
    const res3 = await api.get('/attack/eviltwin/templates')
    templates.value = res3.data.data || []
    
    // 默认选第一个模板
    if(templates.value.length > 0) {
      selectedTemplate.value = templates.value[0]
      form.value.template_html = templates.value[0].content
    }

  } catch (e) {
    ElMessage.error("数据加载失败: " + e.message)
    addLog(`[ERROR] ${e.message}`)
  }
}

// 联动：选中 WiFi 后自动填充表单
const onWifiSelected = () => {
  if (selectedWifi.value) {
    form.value.bssid = selectedWifi.value.bssid
    form.value.ssid = selectedWifi.value.ssid
    form.value.channel = selectedWifi.value.channel
  }
}

// 联动：选中模板后填充 HTML
const onTemplateSelected = () => {
  if (selectedTemplate.value) {
    form.value.template_html = selectedTemplate.value.content
  }
}

const startAttack = async () => {
  if (!form.value.interface || !form.value.ap_interface) return ElMessage.warning("请选择两张网卡")
  if (form.value.interface === form.value.ap_interface) return ElMessage.error("两张网卡不能相同")
  if (!form.value.bssid) return ElMessage.warning("请选择或填写目标 BSSID")

  addLog(`[CMD] Launching Evil Twin...`)
  addLog(`[CONF] Deauth: ${form.value.interface} | AP: ${form.value.ap_interface}`)
  
  try {
    const res = await api.post('/attack/eviltwin/start', form.value)
    if (res.data.status === 'started') {
      isRunning.value = true
      addLog(`[SUCCESS] Attack started! Target: ${form.value.ssid}`)
      ElMessage.success("攻击已启动")
      pollTimer = setInterval(fetchCreds, 3000)
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
    addLog("[CMD] Attack stopped.")
    if (pollTimer) clearInterval(pollTimer)
  } catch (e) {}
}

const fetchCreds = async () => {
  try {
    const res = await api.get('/attack/eviltwin/credentials')
    if (res.data.status === 'success' && res.data.data) {
      res.data.data.forEach(c => {
        if (!capturedCreds.value.includes(c)) {
          capturedCreds.value.push(c)
          ElMessage.success("🔥 捕获到密码！")
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
.custom-scrollbar::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
</style>