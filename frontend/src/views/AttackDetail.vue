<template>
  <div class="min-h-screen bg-[#0b1120] text-gray-300 p-6 flex flex-col font-mono">
    
    <header class="bg-[#1f2937] border border-gray-700 rounded-xl p-4 mb-6 flex justify-between items-center shadow-lg">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 bg-red-900/30 rounded-lg flex items-center justify-center border border-red-500/50">
          <span class="text-2xl">🎯</span>
        </div>
        <div>
          <h1 class="text-xl font-bold text-white tracking-wider">{{ targetInfo.ssid || '正在获取目标信息...' }}</h1>
          <div class="flex gap-4 text-xs text-gray-400 mt-1">
            <span class="bg-black/30 px-2 py-0.5 rounded font-mono">MAC: {{ targetInfo.bssid }}</span>
            <span class="bg-black/30 px-2 py-0.5 rounded text-blue-400">CH: {{ targetInfo.channel }}</span>
            <span class="bg-black/30 px-2 py-0.5 rounded text-green-400">{{ targetInfo.encryption }}</span>
          </div>
        </div>
      </div>
      
      <div class="flex gap-3">
        <button @click="$router.push('/wifi')" class="px-4 py-2 border border-gray-600 rounded hover:bg-gray-700 transition text-sm">
          返回列表
        </button>
      </div>
    </header>

    <div class="flex-1 grid grid-cols-12 gap-6">
      
      <div class="col-span-3 space-y-4">
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl overflow-hidden group hover:border-blue-500 transition">
          <div class="p-4 bg-gray-800/50 border-b border-gray-700 flex justify-between items-center">
            <h3 class="font-bold text-blue-400">📡 握手包捕获</h3>
          </div>
          <div class="p-4 space-y-3">
            <p class="text-xs text-gray-500">发送 Deauth 包迫使客户端重连。</p>
            <button @click="runAttack('handshake')" class="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded font-bold transition shadow-lg shadow-blue-900/20">
              启动 Deauth 攻击
            </button>
          </div>
        </div>

        <div class="bg-[#1f2937] border border-gray-700 rounded-xl overflow-hidden group hover:border-purple-500 transition">
          <div class="p-4 bg-gray-800/50 border-b border-gray-700 flex justify-between items-center">
            <h3 class="font-bold text-purple-400">🎣 钓鱼/双子热点</h3>
          </div>
          <div class="p-4 space-y-3">
            <button @click="runAttack('eviltwin')" class="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs rounded font-bold transition shadow-lg shadow-purple-900/20">
              部署假热点 (Evil Twin)
            </button>
          </div>
        </div>
      </div>

      <div class="col-span-6 flex flex-col gap-4">
        <div class="flex-1 bg-black rounded-xl border border-gray-700 p-4 flex flex-col font-mono text-xs shadow-inner relative h-[500px]">
          <div class="absolute top-2 right-4 text-[10px] text-gray-500 flex items-center gap-2">
            <span class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span> SYSTEM LOG
          </div>
          <div class="flex-1 overflow-y-auto space-y-1 scrollbar-hide" ref="logBox">
            <div v-for="(log, i) in logs" :key="i" class="break-all leading-relaxed">
              <span class="text-green-600 mr-2 select-none">➜</span>
              <span v-html="log" class="text-gray-300"></span>
            </div>
          </div>
        </div>
      </div>

      <div class="col-span-3">
        <div class="bg-gradient-to-b from-[#1f2937] to-[#111827] border border-blue-900/30 rounded-xl h-full flex flex-col shadow-2xl relative overflow-hidden">
          
          <div class="p-4 border-b border-gray-800 flex items-center gap-2">
            <span class="text-xl">🧠</span>
            <h3 class="font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400">
              DeepSeek 战术分析
            </h3>
          </div>

          <div class="p-4 flex-1 overflow-y-auto text-sm space-y-4">
            
            <div v-if="aiThinking" class="flex flex-col items-center justify-center h-40 gap-3 text-blue-400 animate-pulse">
              <div class="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
              <span class="text-xs">AI 正在分析目标特征...</span>
            </div>

            <div v-else-if="!aiResult" class="text-center text-gray-500 mt-10">
              <p>分析失败或尚未开始。</p>
              <button @click="startAIAnalysis" class="mt-4 text-xs border border-gray-600 px-3 py-1 rounded hover:bg-gray-700">重试</button>
            </div>

            <div v-else class="space-y-4 animate-fade-in">
              <div class="bg-red-900/20 border border-red-900/50 p-3 rounded-lg">
                <h4 class="text-xs font-bold mb-1 flex justify-between">
                  <span class="text-red-400">⚠️ 风险评级</span>
                  <span class="bg-red-600 text-white px-2 rounded text-[10px]">{{ aiResult.risk_level }}</span>
                </h4>
                <p class="text-gray-400 text-xs mt-2 leading-relaxed">{{ aiResult.summary || '目标使用了较弱的加密方式...' }}</p>
              </div>

              <div>
                <h4 class="text-blue-400 text-xs font-bold mb-2">AI 推荐攻击向量：</h4>
                <div class="bg-gray-800/50 p-3 rounded border border-gray-700 text-xs text-gray-300 leading-relaxed whitespace-pre-wrap">
                  {{ aiResult.advice }}
                </div>
              </div>

              <div>
                <h4 class="text-purple-400 text-xs font-bold mb-2">社工字典生成规则：</h4>
                <div class="flex flex-wrap gap-2">
                  <span v-for="(rule, idx) in aiResult.dict_rules" :key="idx" 
                        class="bg-gray-800 border border-gray-600 px-2 py-1 rounded text-[10px] text-gray-300 font-mono">
                    {{ rule }}
                  </span>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api'

const route = useRoute()
const bssid = route.params.bssid

// 目标信息 (初始为空)
const targetInfo = ref({
  ssid: '',
  bssid: bssid,
  channel: '-',
  encryption: '-'
})

// AI 分析结果
const aiResult = ref(null)
const aiThinking = ref(true)

const logs = ref(['[SYSTEM] 攻击控制台已就绪。'])
const logBox = ref(null)

// 自动滚动日志
const autoScroll = () => {
  nextTick(() => { if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight })
}

// 1. 获取目标详细信息 (从后端或本地列表缓存)
const loadTargetInfo = async () => {
  try {
    // 这里为了演示简单，我们直接重新请求一次列表，找到这个 BSSID 的信息
    // 实际项目中应该有一个 /wifi/network/{bssid} 的详情接口
    const res = await api.get('/wifi/networks')
    const target = res.data.find(n => n.bssid === bssid)
    if (target) {
      targetInfo.value = target
      logs.value.push(`[INFO] 锁定目标: <span class="text-yellow-400">${target.ssid}</span> (CH: ${target.channel})`)
      
      // 信息获取成功后，立即触发 AI 分析
      startAIAnalysis()
    } else {
      logs.value.push(`[WARN] 未在扫描缓存中找到目标信息，使用默认值。`)
      targetInfo.value.ssid = "Unknown_Target"
      targetInfo.value.encryption = "WPA2"
      startAIAnalysis()
    }
  } catch (e) {
    logs.value.push(`[ERROR] 获取目标信息失败: ${e.message}`)
    aiThinking.value = false
  }
}

// 2. 调用后端 AI 接口
const startAIAnalysis = async () => {
  aiThinking.value = true
  logs.value.push("[AI] 正连接 DeepSeek 神经网络进行战术推演...")
  autoScroll()

  try {
    const res = await api.post('/attack/ai/analyze_target', {
      ssid: targetInfo.value.ssid,
      encryption: targetInfo.value.encryption,
      bssid: targetInfo.value.bssid
    })
    
    // 绑定真实数据！
    aiResult.value = res.data
    logs.value.push(`[AI] 分析完成。风险评级: <span class="text-red-500 font-bold">${res.data.risk_level}</span>`)
    
  } catch (e) {
    logs.value.push(`[ERROR] AI 分析服务无响应: ${e.message}`)
  } finally {
    aiThinking.value = false
    autoScroll()
  }
}

// 3. 执行攻击
const runAttack = async (type) => {
  if (type === 'handshake') {
    logs.value.push(`[CMD] 发送 Deauth 攻击指令... 目标: ${targetInfo.value.bssid}`)
    try {
      await api.post('/wifi/attack/deauth', null, { 
        params: { bssid: bssid, interface: 'wlan0', duration: 60 } 
      })
      logs.value.push("[Kali] 攻击包已发送。正在监听握手包...")
    } catch (e) {
      logs.value.push(`[ERROR] 攻击请求失败: ${e.message}`)
    }
  } else if (type === 'eviltwin') {
    if(!confirm("确定要部署假热点吗？这将断开当前网卡的连接。")) return;
    logs.value.push(`[CMD] 正在配置 Hostapd... SSID: ${targetInfo.value.ssid}`)
    try {
      await api.post('/attack/eviltwin/start', {
        ssid: targetInfo.value.ssid,
        interface: 'wlan0' 
      })
      logs.value.push("[SUCCESS] 钓鱼热点已上线。")
    } catch (e) {
      logs.value.push(`[ERROR] 部署失败: ${e.message}`)
    }
  }
  autoScroll()
}

onMounted(() => {
  loadTargetInfo()
})
</script>

<style scoped>
.scrollbar-hide::-webkit-scrollbar { display: none; }
.animate-fade-in { animation: fadeIn 0.5s ease-in; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>