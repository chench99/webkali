<template>
  <div class="min-h-screen bg-[#0b1120] text-gray-300 p-6 flex flex-col font-mono">
    
    <header class="bg-[#1f2937] border border-gray-700 rounded-xl p-4 mb-6 flex justify-between items-center shadow-lg">
      <div class="flex items-center gap-4">
        <div class="w-12 h-12 bg-red-900/30 rounded-lg flex items-center justify-center border border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.2)]">
          <span class="text-2xl animate-pulse">🎯</span>
        </div>
        
        <div>
          <h1 class="text-xl font-bold text-white tracking-wider flex items-center gap-2">
            {{ targetInfo.ssid || '正在获取目标...' }}
            <span v-if="targetInfo.vendor" class="text-[10px] bg-gray-700 px-1.5 rounded text-gray-400 font-normal border border-gray-600">
              {{ targetInfo.vendor }}
            </span>
          </h1>
          <div class="flex gap-4 text-xs text-gray-400 mt-1">
            <span class="bg-black/30 px-2 py-0.5 rounded font-mono border border-gray-700">MAC: {{ targetInfo.bssid }}</span>
            <span class="bg-black/30 px-2 py-0.5 rounded text-blue-400 border border-blue-900/30">CH: {{ targetInfo.channel }}</span>
            <span class="bg-black/30 px-2 py-0.5 rounded text-green-400 border border-green-900/30">{{ targetInfo.encryption }}</span>
          </div>
        </div>
      </div>
      
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2 bg-black/20 px-3 py-1.5 rounded border border-gray-600">
          <span class="text-xs font-bold text-gray-400">⚔️ 攻击网卡:</span>
          <select 
            v-model="selectedInterface"
            class="bg-transparent text-yellow-400 text-xs font-mono focus:outline-none cursor-pointer w-32"
          >
            <option value="" disabled>选择网卡...</option>
            <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
              {{ iface.display || iface.name }}
            </option>
          </select>
        </div>

        <button @click="$router.push('/wifi')" class="px-4 py-2 border border-gray-600 rounded hover:bg-gray-700 transition text-sm flex items-center gap-2">
          <span>↩</span> 返回列表
        </button>
      </div>
    </header>

    <div class="flex-1 grid grid-cols-12 gap-6">
      
      <div class="col-span-3 space-y-4">
        
        <div class="bg-[#1f2937] border border-gray-700 rounded-xl overflow-hidden group hover:border-green-500 transition relative">
          <div class="absolute top-0 right-0 w-16 h-16 bg-green-500/10 rounded-bl-full -mr-8 -mt-8 transition group-hover:bg-green-500/20"></div>
          
          <div class="p-4 bg-gray-800/50 border-b border-gray-700 flex justify-between items-center">
            <h3 class="font-bold text-green-400 flex items-center gap-2">
              <span>🔐</span> 握手包捕获
            </h3>
          </div>
          
          <div class="p-4 space-y-3">
            <p class="text-[10px] text-gray-500 leading-tight">
              全自动流程：监听 -> Deauth 诱骗 -> 抓包 -> 格式转换 (.hc22000)。
            </p>
            
            <div v-if="!captureSuccess">
              <button 
                @click="runAttack('capture')" 
                class="w-full py-2.5 bg-green-600 hover:bg-green-500 text-white text-xs rounded font-bold transition shadow-lg shadow-green-900/20 flex justify-center items-center gap-2"
                :disabled="isRunning"
                :class="{'opacity-50 cursor-not-allowed': isRunning}"
              >
                <span v-if="isRunning && currentAttack === 'capture'" class="animate-spin">⏳</span>
                {{ isRunning && currentAttack === 'capture' ? '正在捕获 (约40s)...' : '🚀 启动捕获 (Capture)' }}
              </button>
            </div>

            <div v-else class="animate-fade-in-up space-y-3">
              <div class="grid grid-cols-2 gap-2">
                <button 
                  v-if="capturedFiles.cap"
                  @click="downloadFile(capturedFiles.cap)"
                  class="py-2 bg-blue-600 hover:bg-blue-500 text-white text-[10px] rounded font-bold transition flex flex-col items-center justify-center border border-blue-400/30"
                  title="下载原始数据包 (Wireshark)"
                >
                  <span class="flex items-center gap-1">📥 .CAP</span>
                  <span class="opacity-70 scale-75 font-normal">原始包</span>
                </button>
                
                <button 
                  v-if="capturedFiles.hash"
                  @click="downloadFile(capturedFiles.hash)"
                  class="py-2 bg-purple-600 hover:bg-purple-500 text-white text-[10px] rounded font-bold transition flex flex-col items-center justify-center border border-purple-400/30"
                  title="下载 Hashcat 格式 (直接跑字典)"
                >
                  <span class="flex items-center gap-1">📥 .HC22000</span>
                  <span class="opacity-70 scale-75 font-normal">Hashcat</span>
                </button>
              </div>

              <button 
                @click="$router.push('/crack')" 
                class="w-full py-2.5 bg-gradient-to-r from-yellow-600 to-orange-600 hover:from-yellow-500 hover:to-orange-500 text-white text-xs rounded font-bold transition shadow-lg shadow-orange-900/30 flex justify-center items-center gap-2 border border-orange-400/30"
              >
                <span>🔑</span> ✅ 前往破解中心
              </button>
            </div>
          </div>
        </div>

        <div class="bg-[#1f2937] border border-gray-700 rounded-xl overflow-hidden group hover:border-blue-500 transition">
          <div class="p-4 bg-gray-800/50 border-b border-gray-700 flex justify-between items-center">
            <h3 class="font-bold text-blue-400 flex items-center gap-2">
              <span>📡</span> 干扰攻击 (Deauth)
            </h3>
          </div>
          <div class="p-4 space-y-3">
            <p class="text-[10px] text-gray-500">发送解除认证帧，强制客户端断线重连。</p>
            <div class="flex items-center gap-2 mb-2">
              <label class="text-xs text-gray-400">持续时长(秒):</label>
              <input type="number" v-model="attackDuration" class="bg-black/30 border border-gray-600 rounded px-2 py-1 text-xs w-16 text-center text-white focus:border-blue-500 outline-none">
            </div>
            <button 
              @click="runAttack('deauth')" 
              class="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded font-bold transition shadow-lg shadow-blue-900/20 flex justify-center items-center gap-2"
              :disabled="isRunning"
              :class="{'opacity-50 cursor-not-allowed': isRunning}"
            >
              <span v-if="isRunning && currentAttack === 'deauth'" class="animate-spin">🌀</span>
              {{ isRunning && currentAttack === 'deauth' ? '攻击进行中...' : '⚡ 发动 Flood 攻击' }}
            </button>
          </div>
        </div>

        <div class="bg-[#1f2937] border border-gray-700 rounded-xl overflow-hidden group hover:border-purple-500 transition opacity-80 hover:opacity-100">
          <div class="p-4 bg-gray-800/50 border-b border-gray-700 flex justify-between items-center">
            <h3 class="font-bold text-purple-400 flex items-center gap-2">
              <span>🎣</span> 双子热点 (Evil Twin)
            </h3>
          </div>
          <div class="p-4 space-y-3">
            <button 
              @click="runAttack('eviltwin')" 
              class="w-full py-2.5 bg-purple-600 hover:bg-purple-500 text-white text-xs rounded font-bold transition shadow-lg shadow-purple-900/20 border border-purple-400/30"
            >
              👻 部署伪造热点
            </button>
          </div>
        </div>

      </div>

      <div class="col-span-6 flex flex-col gap-4">
        <div class="flex-1 bg-black rounded-xl border border-gray-700 p-4 flex flex-col font-mono text-xs shadow-inner relative h-[600px]">
          
          <div class="absolute top-0 left-0 right-0 h-8 bg-gray-900/80 border-b border-gray-800 rounded-t-xl flex items-center px-4 justify-between">
            <span class="text-gray-500 flex items-center gap-2">
              <span class="w-2 h-2 bg-red-500 rounded-full"></span>
              <span class="w-2 h-2 bg-yellow-500 rounded-full"></span>
              <span class="w-2 h-2 bg-green-500 rounded-full"></span>
            </span>
            <div class="text-[10px] text-gray-500 flex items-center gap-2">
              <span class="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span> SSH CONSOLE / AGENT LOGS
            </div>
          </div>

          <div class="flex-1 overflow-y-auto space-y-1.5 scrollbar-thin mt-8 pr-2" ref="logBox">
            <div v-for="(log, i) in logs" :key="i" class="break-all leading-relaxed font-mono">
              <span class="text-green-600 mr-2 select-none font-bold opacity-70">➜</span>
              <span v-html="log" class="text-gray-300"></span>
            </div>
            <div v-if="isRunning" class="animate-pulse text-gray-500 mt-2">_</div>
          </div>
        </div>
      </div>

      <div class="col-span-3">
        <div class="bg-gradient-to-b from-[#1f2937] to-[#111827] border border-blue-900/30 rounded-xl h-full flex flex-col shadow-2xl relative overflow-hidden">
          
          <div class="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-full blur-3xl -mr-10 -mt-10"></div>

          <div class="p-4 border-b border-gray-800 flex items-center gap-2 relative z-10">
            <span class="text-xl">🧠</span>
            <h3 class="font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400">
              DeepSeek 战术分析
            </h3>
          </div>

          <div class="p-4 flex-1 overflow-y-auto text-sm space-y-4 relative z-10 scrollbar-thin">
            
            <div v-if="aiThinking" class="flex flex-col items-center justify-center h-40 gap-3 text-blue-400 animate-pulse">
              <div class="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
              <span class="text-xs font-bold">神经网络正在推理...</span>
              <span class="text-[10px] text-gray-500">Analysing Encryption & Vectors...</span>
            </div>

            <div v-else-if="!aiResult" class="text-center text-gray-500 mt-10">
              <p>暂无分析数据。</p>
              <button @click="startAIAnalysis" class="mt-4 text-xs border border-gray-600 px-3 py-1 rounded hover:bg-gray-700 transition">
                🚀 立即分析
              </button>
            </div>

            <div v-else class="space-y-4 animate-fade-in">
              <div class="bg-red-900/20 border border-red-900/50 p-3 rounded-lg relative overflow-hidden">
                <div class="absolute top-0 left-0 w-1 h-full bg-red-600"></div>
                <h4 class="text-xs font-bold mb-1 flex justify-between items-center">
                  <span class="text-red-400 pl-2">⚠️ 风险评级</span>
                  <span class="bg-red-600 text-white px-2 py-0.5 rounded text-[10px] shadow">{{ aiResult.risk_level }}</span>
                </h4>
                <p class="text-gray-400 text-[10px] mt-2 leading-relaxed pl-2">{{ aiResult.summary }}</p>
              </div>

              <div>
                <h4 class="text-blue-400 text-xs font-bold mb-2 flex items-center gap-1">
                  <span>💡</span> 推荐攻击向量
                </h4>
                <div class="bg-gray-800/50 p-3 rounded border border-gray-700 text-xs text-gray-300 leading-relaxed whitespace-pre-wrap font-mono">
                  {{ aiResult.advice }}
                </div>
              </div>

              <div>
                <h4 class="text-purple-400 text-xs font-bold mb-2 flex items-center gap-1">
                  <span>📖</span> 字典生成规则
                </h4>
                <div class="flex flex-wrap gap-2">
                  <span v-for="(rule, idx) in aiResult.dict_rules" :key="idx" 
                        class="bg-gray-800 border border-gray-600 px-2 py-1 rounded text-[10px] text-gray-300 font-mono select-all hover:border-purple-500 cursor-pointer transition">
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
import { useRoute, useRouter } from 'vue-router'
// 引入所有 API (使用命名导入)
import { 
  getInterfaces, 
  getWifiList, 
  sendDeauth, 
  captureHandshake, 
  startEvilTwin, 
  analyzeTargetAI 
} from '@/api'

const route = useRoute()
const router = useRouter()
const bssid = route.params.bssid

// 1. 状态定义
const targetInfo = ref({
  ssid: '',
  bssid: bssid,
  channel: '1',
  encryption: '-',
  vendor: ''
})

const interfaces = ref([])
const selectedInterface = ref('') // 动态网卡
const attackDuration = ref(60)

const logs = ref(['[SYSTEM] 攻击控制台初始化完成。'])
const logBox = ref(null)

const isRunning = ref(false)
const currentAttack = ref('')

// 捕获状态管理
const captureSuccess = ref(false)
const capturedFiles = ref({ cap: null, hash: null }) // 存储后端返回的文件名

const aiResult = ref(null)
const aiThinking = ref(false)

// 2. 辅助函数
const autoScroll = () => {
  nextTick(() => { if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight })
}

const addLog = (msg, type = 'info') => {
  let color = 'text-gray-300'
  if (type === 'cmd') color = 'text-yellow-400 font-bold'
  if (type === 'success') color = 'text-green-400 font-bold'
  if (type === 'error') color = 'text-red-400'
  if (type === 'kali') color = 'text-blue-300'
  
  logs.value.push(`<span class="${color}">${msg}</span>`)
  autoScroll()
}

// 3. 下载文件
const downloadFile = (filename) => {
  if (!filename) return
  // 直接在新窗口打开后端下载链接
  const url = `/api/v1/attack/download/${filename}`
  window.open(url, '_blank')
}

// 4. 加载网卡列表
const loadInterfaces = async () => {
  try {
    const res = await getInterfaces()
    if (res.data && res.data.interfaces) {
      interfaces.value = res.data.interfaces
      
      // 智能选择 Monitor 网卡
      const monitorIface = interfaces.value.find(i => i.mode === 'Monitor' || i.name.includes('mon'))
      if (monitorIface) {
        selectedInterface.value = monitorIface.name
        addLog(`[INIT] 自动选定攻击网卡: ${monitorIface.name} (Monitor)`, 'success')
      } else if (interfaces.value.length > 0) {
        selectedInterface.value = interfaces.value[0].name
        addLog(`[WARN] 未检测到 Monitor 模式网卡，默认选择: ${selectedInterface.value}`, 'error')
      } else {
        addLog(`[FATAL] 未检测到可用无线网卡！请检查 Agent 连接。`, 'error')
      }
    }
  } catch (e) {
    addLog(`[ERROR] 网卡列表获取失败: ${e.message}`, 'error')
  }
}

// 5. 加载目标信息
const loadTargetInfo = async () => {
  try {
    const res = await getWifiList()
    const target = res.data.find(n => n.bssid === bssid)
    if (target) {
      targetInfo.value = target
      addLog(`[INFO] 目标锁定: <span class="text-white">${target.ssid}</span>`, 'info')
      addLog(`[INFO] 信道: ${target.channel} | 加密: ${target.encryption}`, 'info')
      
      // 信息加载成功后，自动开始 AI 分析
      if (!aiResult.value) startAIAnalysis()
    } else {
      addLog(`[WARN] 本地缓存未找到目标，使用默认参数。`, 'error')
      targetInfo.value.ssid = "Unknown"
    }
  } catch (e) {
    addLog(`[ERROR] 目标信息加载失败: ${e.message}`, 'error')
  }
}

// 6. AI 分析
const startAIAnalysis = async () => {
  aiThinking.value = true
  addLog("[AI] 正在连接 DeepSeek 神经网络...", 'kali')
  
  try {
    const res = await analyzeTargetAI({
      ssid: targetInfo.value.ssid,
      encryption: targetInfo.value.encryption,
      bssid: targetInfo.value.bssid
    })
    aiResult.value = res.data
    addLog(`[AI] 分析完成。风险等级: ${res.data.risk_level}`, 'success')
  } catch (e) {
    addLog(`[AI] 分析服务无响应: ${e.message}`, 'error')
  } finally {
    aiThinking.value = false
  }
}

// 7. 核心攻击逻辑
const runAttack = async (type) => {
  if (!selectedInterface.value) {
    addLog(`[ERROR] 请先在右上角选择攻击网卡！`, 'error')
    return
  }

  isRunning.value = true
  currentAttack.value = type
  
  try {
    // === Deauth 攻击 ===
    if (type === 'deauth') {
      addLog(`[CMD] 启动 Deauth 干扰... 目标: ${targetInfo.value.bssid}`, 'cmd')
      addLog(`[CFG] 网卡: ${selectedInterface.value} | 时长: ${attackDuration.value}s`, 'kali')
      
      await sendDeauth({
        bssid: targetInfo.value.bssid,
        interface: selectedInterface.value,
        channel: String(targetInfo.value.channel),
        duration: parseInt(attackDuration.value)
      })
      
      addLog("[Kali] 攻击指令已下发 (PID: Running)。", 'success')
      
    // === 握手包捕获 ===
    } else if (type === 'capture') {
      addLog(`[CMD] 启动握手包捕获序列 (耗时约40秒)...`, 'cmd')
      addLog(`[INFO] 阶段: 锁定信道 -> 诱骗重连 -> 抓包`, 'kali')
      
      const res = await captureHandshake({
        bssid: targetInfo.value.bssid,
        interface: selectedInterface.value,
        channel: String(targetInfo.value.channel),
        duration: 35 // 给后端 35秒执行时间
      })
      
      if (res.data.status === 'success') {
        addLog(`[SUCCESS] ✅ 握手包捕获成功！`, 'success')
        
        // 存储文件名
        capturedFiles.value.cap = res.data.cap_file
        capturedFiles.value.hash = res.data.hash_file
        
        if(res.data.hash_file) {
          addLog(`[INFO] Hashcat 格式转换完成 (.hc22000)`, 'kali')
        } else {
          addLog(`[WARN] 未生成 .hc22000 文件 (Kali 可能缺失 hcxtools)`, 'error')
        }
        
        captureSuccess.value = true // 切换 UI 状态
      } else {
        addLog(`[FAIL] 捕获失败: ${res.data.msg}`, 'error')
        if (res.data.debug) addLog(`[DEBUG] ${res.data.debug}`, 'kali')
      }

    // === 钓鱼热点 ===
    } else if (type === 'eviltwin') {
      if(!confirm("⚠️ 警告：启动双子热点将占用网卡，可能导致 SSH 短暂断开。是否继续？")) {
        isRunning.value = false
        return
      }
      addLog(`[CMD] 部署 Rogue AP: ${targetInfo.value.ssid}`, 'cmd')
      await startEvilTwin({
        ssid: targetInfo.value.ssid,
        interface: selectedInterface.value
      })
      addLog("[SUCCESS] 钓鱼热点已启动 (Mock Mode)。", 'success')
    }

  } catch (e) {
    addLog(`[ERROR] 请求异常: ${e.message}`, 'error')
  } finally {
    if (type !== 'deauth') isRunning.value = false
    // Deauth 立即释放按钮
    setTimeout(() => { if (type === 'deauth') isRunning.value = false }, 2000)
  }
}

// 8. 生命周期挂载
onMounted(async () => {
  await loadInterfaces() // 先加载网卡
  await loadTargetInfo() // 再加载目标
})
</script>

<style scoped>
/* 滚动条美化 */
.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-track { background: #111827; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: #374151; border-radius: 2px; }
.animate-fade-in-up { animation: fadeInUp 0.5s ease-out; }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
</style>