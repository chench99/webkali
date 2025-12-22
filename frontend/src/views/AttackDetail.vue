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
              发送攻击指令
            </button>
          </div>
        </div>

        <div class="bg-[#1f2937] border border-gray-700 rounded-xl overflow-hidden group hover:border-green-500 transition">
          <div class="p-4 bg-gray-800/50 border-b border-gray-700 flex justify-between items-center">
            <h3 class="font-bold text-green-400">📦 握手包导入</h3>
          </div>
          <div class="p-4 space-y-3">
            <input
              type="file"
              accept=".cap,.pcap,.pcapng"
              class="block w-full text-xs text-gray-300 file:mr-4 file:py-2 file:px-3 file:rounded file:border-0 file:text-xs file:font-bold file:bg-green-600 file:text-white hover:file:bg-green-500"
              @change="onHandshakeFileChange"
            />
            <div class="text-[10px] text-gray-500">
              仅用于导入你已合法获取的抓包文件（.cap/.pcap/.pcapng）。
            </div>
            <div class="border border-gray-700 rounded p-2 bg-black/20 max-h-40 overflow-y-auto">
              <div v-if="handshakeItems.length === 0" class="text-xs text-gray-500 text-center py-2">暂无文件</div>
              <div v-for="item in handshakeItems" :key="item.filename" class="flex items-center justify-between gap-2 py-1">
                <div class="text-[10px] text-gray-300 font-mono truncate" :title="item.filename">{{ item.filename }}</div>
                <button
                  class="text-[10px] px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-white"
                  @click="downloadHandshake(item.filename)"
                >
                  下载
                </button>
              </div>
            </div>
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

// 目标信息
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
const handshakeItems = ref([])

const autoScroll = () => {
  nextTick(() => { if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight })
}

// 1. 获取目标信息
const loadTargetInfo = async () => {
  try {
    const res = await api.get('/wifi/networks')
    const target = res.data.find(n => n.bssid === bssid)
    if (target) {
      targetInfo.value = target
      logs.value.push(`[INFO] 锁定目标: <span class="text-yellow-400">${target.ssid}</span> (CH: ${target.channel})`)
      startAIAnalysis()
    } else {
      logs.value.push(`[WARN] 未在缓存中找到目标，使用默认值。`)
      targetInfo.value.ssid = "Unknown"
      targetInfo.value.encryption = "WPA2"
      startAIAnalysis()
    }
  } catch (e) {
    logs.value.push(`[ERROR] 获取目标失败: ${e.message}`)
    aiThinking.value = false
  }
}

const loadHandshakeItems = async () => {
  try {
    const res = await api.get('/wifi/handshake/list', { params: { bssid } })
    handshakeItems.value = res.data?.items || []
  } catch (e) {
    handshakeItems.value = []
  }
}

const onHandshakeFileChange = async (evt) => {
  const f = evt?.target?.files?.[0]
  if (!f) return
  const form = new FormData()
  form.append('file', f)
  form.append('bssid', bssid)
  form.append('ssid', targetInfo.value.ssid || '')
  logs.value.push(`[UPLOAD] 正在上传抓包文件: ${f.name}`)
  autoScroll()

  try {
    await api.post('/wifi/handshake/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    logs.value.push('[UPLOAD] 上传成功。')
    await loadHandshakeItems()
  } catch (e) {
    logs.value.push(`[ERROR] 上传失败: ${e.message}`)
  } finally {
    autoScroll()
    evt.target.value = ''
  }
}

const downloadHandshake = (filename) => {
  const url = `/api/v1/wifi/handshake/download/${encodeURIComponent(filename)}`
  window.open(url, '_blank')
}

// 2. 调用 AI 分析 (修正了接口地址)
const startAIAnalysis = async () => {
  aiThinking.value = true
  logs.value.push("[AI] 正连接 DeepSeek 神经网络进行战术推演...")
  autoScroll()

  try {
    // 修正：地址改为 /ai/analyze_target
    const res = await api.post('/ai/analyze_target', {
      ssid: targetInfo.value.ssid,
      encryption: targetInfo.value.encryption,
      bssid: targetInfo.value.bssid
    })
    
    aiResult.value = res.data
    logs.value.push(`[AI] 分析完成。风险评级: <span class="text-red-500 font-bold">${res.data.risk_level}</span>`)
    
  } catch (e) {
    logs.value.push(`[ERROR] AI 分析失败: ${e.message}`)
    aiResult.value = null
  } finally {
    aiThinking.value = false
    autoScroll()
  }
}

// 3. 攻击逻辑
const runAttack = async (type) => {
  if (type === 'handshake') {
    logs.value.push(`[CMD] 发送 Deauth... 目标: ${targetInfo.value.bssid}`)
    try {
      const res = await api.post('/wifi/attack/deauth', null, { 
        params: { bssid: bssid, interface: 'wlan0', duration: 60 } 
      })
      if (res?.data?.status === 'disabled') {
        logs.value.push(`[WARN] ${res.data.message}`)
      } else {
        logs.value.push("[Kali] 指令已提交。")
      }
    } catch (e) {
      logs.value.push(`[ERROR] 攻击失败: ${e.message}`)
    }
  } else if (type === 'eviltwin') {
    if(!confirm("确定要部署假热点吗？")) return;
    logs.value.push(`[WARN] 该能力默认未启用。仅在获得明确授权与合规配置后才可开启。`)
  }
  autoScroll()
}

onMounted(() => {
  loadTargetInfo()
  loadHandshakeItems()
})
</script>

<style scoped>
.scrollbar-hide::-webkit-scrollbar { display: none; }
.animate-fade-in { animation: fadeIn 0.5s ease-in; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>
