<template>
  <div class="wifi-container p-6 bg-[#0b1120] text-gray-200 min-h-screen font-sans">
    
    <div class="flex justify-between items-end mb-6 border-b border-gray-800 pb-4">
      <div>
        <h2 class="text-2xl font-bold flex items-center gap-3 text-blue-400">
          <span class="text-3xl">📡</span> 无线渗透控制台
          <span class="text-xs border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 rounded text-blue-300">Heartbeat C2 Mode</span>
        </h2>
        <div class="text-gray-500 text-xs mt-2 flex gap-4 font-mono">
          <span>Agent状态: <span :class="hasAgent ? 'text-green-400':'text-red-400'">{{ agentStatusText }}</span></span>
          <span>当前任务: <span class="text-yellow-400">{{ currentTask }}</span></span>
          <span v-if="monitoringBSSID">正在监听: {{ monitoringBSSID }}</span>
        </div>
      </div>
    </div>

    <div class="flex gap-4 justify-between items-center mb-6 bg-[#111827] p-4 rounded-xl border border-gray-700/50 shadow-lg">
      <div class="flex items-center gap-3">
        <span class="text-sm font-bold text-gray-400">选择网卡:</span>
        <div class="relative">
          <select 
            v-model="selectedInterface" 
            class="bg-gray-800 border border-gray-600 px-3 py-1.5 rounded text-sm w-56 focus:outline-none focus:border-blue-500 transition"
          >
            <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
              {{ iface.display }}
            </option>
          </select>
        </div>
        <button @click="fetchInterfaces" class="text-gray-400 hover:text-white transition p-1 rounded hover:bg-gray-700" title="刷新网卡">
          ↻
        </button>
      </div>

      <button 
        class="px-6 py-2 rounded-lg bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white font-bold text-sm shadow-lg shadow-blue-900/30 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        :disabled="isScanning || !hasAgent || currentTask !== 'idle'"
        @click="startScan"
      >
        <span v-if="isScanning" class="animate-spin">⏳</span>
        {{ isScanning ? '全频段扫描中 (10s)...' : '执行扫描 (2.4G/5G)' }}
      </button>
    </div>

    <div class="bg-[#111827] rounded-xl shadow-xl overflow-hidden border border-gray-700/50 relative">
      <div v-if="isScanning" class="absolute inset-0 bg-black/60 z-10 flex items-center justify-center backdrop-blur-sm">
        <div class="text-center">
          <div class="text-4xl animate-bounce mb-2">📡</div>
          <p class="text-blue-400 font-bold">正在扫描环境中...</p>
          <p class="text-xs text-gray-500 mt-1">请等待 Agent 回传数据</p>
        </div>
      </div>

      <table class="w-full text-left text-sm">
        <thead class="bg-gray-800 text-gray-400 uppercase font-mono text-xs tracking-wider">
          <tr>
            <th class="p-4">ESSID (名称)</th>
            <th class="p-4">BSSID (MAC)</th>
            <th class="p-4">信道/频段</th>
            <th class="p-4">加密</th>
            <th class="p-4 text-green-400">在线客户端</th>
            <th class="p-4">信号强度</th>
            <th class="p-4 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-700/50">
          <tr v-if="networks.length === 0" class="text-center text-gray-500">
            <td colspan="7" class="p-12">
              暂无数据，请确认 Agent 在线并点击“执行扫描”
            </td>
          </tr>
          
          <tr v-for="(net, index) in networks" :key="index" class="hover:bg-gray-800/50 transition group">
            <td class="p-4">
              <div class="font-bold text-white">{{ net.ssid }}</div>
            </td>
            
            <td class="p-4 font-mono text-xs text-gray-400">{{ net.bssid }}</td>
            
            <td class="p-4">
              <div class="flex items-center gap-2">
                <span class="font-mono font-bold text-gray-300">{{ net.channel }}</span>
                <span 
                  class="text-[10px] px-1.5 py-0.5 rounded border font-mono"
                  :class="getBandClass(net.channel)"
                >
                  {{ net.channel > 14 ? '5G' : '2.4G' }}
                </span>
              </div>
            </td>
            
            <td class="p-4">
              <span class="px-2 py-0.5 rounded text-xs border bg-opacity-20" :class="getEncClass(net.encryption)">
                {{ net.encryption }}
              </span>
            </td>

            <td class="p-4">
              <div v-if="net.client_count > 0" class="flex items-center gap-2 text-green-400 font-bold font-mono">
                <span>{{ net.client_count }} Devices</span>
                <span class="relative flex h-2 w-2">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                </span>
              </div>
              <span v-else class="text-gray-600 text-xs">-</span>
            </td>

            <td class="p-4">
              <div class="flex items-center gap-2">
                <div class="w-16 bg-gray-700 rounded-full h-1.5 overflow-hidden">
                  <div class="h-full transition-all" :class="getSignalColor(net.signal)" :style="{ width: getSignalPercent(net.signal) + '%' }"></div>
                </div>
                <span class="text-xs font-mono w-8 text-right">{{ net.signal }}</span>
              </div>
            </td>

            <td class="p-4 text-right">
              <div class="flex justify-end gap-2">
                <button 
                  v-if="monitoringBSSID === net.bssid"
                  class="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 text-white rounded text-xs animate-pulse shadow-lg shadow-yellow-900/20"
                  @click="stopMonitor"
                >
                  停止监听
                </button>
                <button 
                  v-else
                  class="px-3 py-1 border border-gray-600 hover:bg-gray-700 text-gray-300 rounded text-xs transition"
                  :disabled="currentTask !== 'idle'"
                  @click="startMonitor(net)"
                >
                  查看监听
                </button>
                
                <button 
                  class="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded text-xs font-bold shadow-lg shadow-red-900/20" 
                  @click="$router.push({ name: 'AttackDetail', params: { bssid: net.bssid } })"
                >
                  攻击
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <transition name="slide-up">
      <div v-if="monitoringBSSID" class="fixed bottom-6 right-6 w-96 bg-[#1f2937] border border-yellow-500/30 rounded-xl shadow-2xl z-50 flex flex-col max-h-[500px]">
        <div class="p-4 bg-gray-800/80 border-b border-gray-700 rounded-t-xl flex justify-between items-center backdrop-blur-sm">
          <div>
            <h3 class="font-bold text-yellow-500 flex items-center gap-2">
              <span class="animate-pulse">🔴</span> 实时监听中
            </h3>
            <div class="text-xs text-gray-400 font-mono mt-1">Target: {{ monitoringBSSID }}</div>
          </div>
          <button @click="stopMonitor" class="text-gray-400 hover:text-white">✕</button>
        </div>

        <div class="p-4 overflow-y-auto flex-1 space-y-2 custom-scrollbar">
          <div v-if="monitoredClients.length === 0" class="text-center text-gray-500 py-4 text-sm">
            等待客户端数据回传...<br>
            <span class="text-xs text-gray-600">(Agent 每 2 秒上报一次)</span>
          </div>

          <div v-for="client in monitoredClients" :key="client.client_mac" class="bg-black/20 p-3 rounded border border-gray-700/50 flex justify-between items-center animate-fade-in">
            <div>
              <div class="text-blue-300 font-mono font-bold text-sm">{{ client.client_mac }}</div>
              <div class="text-[10px] text-gray-500 mt-0.5">上次活跃: {{ formatTime(client.last_seen) }}</div>
            </div>
            <div class="text-right">
              <div class="text-green-400 text-xs font-bold font-mono">{{ client.packet_count }} Pkts</div>
              <div class="text-gray-500 text-xs font-mono">{{ client.signal }} dBm</div>
            </div>
          </div>
        </div>
      </div>
    </transition>

  </div>
</template>

<script>
import api from '@/api' // 使用封装好的 api 实例

export default {
  name: "WiFiPanel",
  data() {
    return {
      isScanning: false,
      selectedInterface: "",
      interfaces: [],
      networks: [],
      currentTask: 'idle',
      
      monitoringBSSID: null, // 当前正在监听的 BSSID
      monitoredClients: [],  // 数据库回传的客户端列表
      
      pollTimer: null // 轮询定时器
    };
  },
  computed: {
    hasAgent() { 
      return this.interfaces.length > 0 && this.interfaces[0].name !== 'waiting'; 
    },
    agentStatusText() {
      if (!this.hasAgent) return '离线 / 等待连接...';
      return 'ONLINE';
    }
  },
  mounted() {
    this.fetchInterfaces();
    this.fetchNetworks(); // 加载上次缓存
    
    // 启动全局轮询 (3秒一次)
    this.pollTimer = setInterval(() => {
      // 1. 刷新网卡状态 (防掉线)
      if (!this.isScanning) this.fetchInterfaces();
      
      // 2. 如果正在监听，拉取客户端数据
      if (this.monitoringBSSID) {
        this.fetchMonitoredClients();
      }
    }, 3000);
  },
  beforeUnmount() {
    if (this.pollTimer) clearInterval(this.pollTimer);
  },
  methods: {
    // 获取网卡
    async fetchInterfaces() {
      try {
        const res = await api.get('/wifi/interfaces');
        if (res.data.interfaces) {
          this.interfaces = res.data.interfaces;
          // 自动选中第一个可用网卡
          if (!this.selectedInterface && this.hasAgent) {
            this.selectedInterface = this.interfaces[0].name;
          }
        }
      } catch (e) {}
    },

    // 获取缓存的网络列表
    async fetchNetworks() {
       if (this.currentTask === 'idle' && !this.isScanning) {
           try {
               const res = await api.get('/wifi/networks');
               if(res.data) this.networks = res.data;
           } catch(e) {}
       }
    },

    // [交互] 开始扫描
    async startScan() {
      if (!this.selectedInterface) return alert("请先选择网卡");
      
      this.isScanning = true;
      this.networks = []; // 清空列表，给用户视觉反馈
      
      try {
        // 请求后端触发扫描 (会阻塞10-20秒)
        const res = await api.post('/wifi/scan/start', { interface: this.selectedInterface });
        
        if (res.data.status === 'success') {
            this.networks = res.data.networks;
            // 排序：在线人数 > 信号强度
            this.networks.sort((a, b) => b.client_count - a.client_count || b.signal - a.signal);
        } else {
            alert("扫描失败: " + (res.data.message || '超时'));
        }
      } catch (e) {
        alert("请求错误: " + e.message);
      } finally {
        this.isScanning = false;
        // 更新一下当前任务状态
        this.currentTask = 'idle';
      }
    },
    
    // [交互] 开始监听
    async startMonitor(net) {
      // 乐观更新 UI
      this.monitoringBSSID = net.bssid;
      this.currentTask = 'monitor_target';
      this.monitoredClients = []; 
      
      try {
        await api.post('/wifi/monitor/start', {
          bssid: net.bssid,
          channel: net.channel,
          interface: this.selectedInterface
        });
      } catch (e) {
        alert("指令下发失败");
        this.stopMonitor();
      }
    },

    // [交互] 停止监听
    async stopMonitor() {
      this.monitoringBSSID = null;
      this.currentTask = 'idle';
      try {
        await api.post('/wifi/monitor/stop');
      } catch (e) {}
    },

    // [数据] 拉取监听数据
    async fetchMonitoredClients() {
      if (!this.monitoringBSSID) return;
      try {
        const res = await api.get(`/wifi/monitor/clients/${this.monitoringBSSID}`);
        if (res.data) {
          this.monitoredClients = res.data;
        }
      } catch (e) {}
    },

    // === 格式化工具 ===
    getBandClass(channel) {
      if (channel > 14) return 'bg-purple-900/50 text-purple-300 border-purple-500/30';
      return 'bg-blue-900/50 text-blue-300 border-blue-500/30';
    },
    getEncClass(enc) {
      if (!enc) return '';
      enc = enc.trim();
      if (enc === 'OPEN') return 'border-red-500 text-red-400 bg-red-900/20';
      if (enc.includes('WPA2')) return 'border-green-500/30 text-green-400 bg-green-900/10';
      return 'border-gray-600 text-gray-400';
    },
    getSignalPercent(sig) { 
      return Math.min(100, Math.max(0, (parseInt(sig) + 100) * 2)); 
    },
    getSignalColor(sig) {
      const p = this.getSignalPercent(sig);
      if (p > 70) return 'bg-green-500';
      if (p > 40) return 'bg-yellow-500';
      return 'bg-red-500';
    },
    formatTime(utcStr) {
      if (!utcStr) return '-';
      return new Date(utcStr).toLocaleTimeString();
    }
  }
};
</script>

<style scoped>
/* 列表滑入动画 */
.slide-up-enter-active, .slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from, .slide-up-leave-to { transform: translateY(100%); opacity: 0; }

/* 客户端单项淡入 */
.animate-fade-in { animation: fadeIn 0.5s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }

/* 自定义滚动条 */
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
</style>