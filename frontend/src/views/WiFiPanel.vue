<template>
  <div class="wifi-container p-6 bg-[#0b1120] text-gray-200 min-h-screen font-sans">
    
    <div class="flex justify-between items-end mb-6 border-b border-gray-800 pb-4">
      <div>
        <h2 class="text-2xl font-bold flex items-center gap-3 text-blue-400">
          <span class="text-3xl">📡</span> 无线渗透控制台
          <span class="text-xs border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 rounded text-blue-300">持久化数据库模式</span>
        </h2>
        <div class="text-gray-500 text-xs mt-2 flex gap-4 font-mono">
          <span>Agent 状态: <span :class="hasAgent ? 'text-green-400':'text-red-400'">{{ agentStatusText }}</span></span>
          <span>当前任务: <span class="text-yellow-400">{{ currentTask }}</span></span>
        </div>
      </div>
      <div>
        <button 
          v-if="!hasAgent"
          class="bg-red-900/30 hover:bg-red-900/50 border border-red-700 text-red-300 px-4 py-2 rounded text-xs font-bold transition flex items-center gap-2"
          @click="deployAgent"
          :disabled="isDeploying"
        >
          <span v-if="isDeploying" class="animate-spin">🔄</span>
          {{ isDeploying ? '正在部署 (SSH)...' : '🛠️ 一键部署 Agent' }}
        </button>
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
        {{ isScanning ? '全网扫描中 (15s)...' : '执行扫描 (含5G)' }}
      </button>
    </div>

    <div class="bg-[#111827] rounded-xl shadow-xl overflow-hidden border border-gray-700/50 relative">
      <div v-if="isScanning" class="absolute inset-0 bg-black/60 z-10 flex items-center justify-center backdrop-blur-sm">
        <div class="text-center">
          <div class="text-4xl animate-bounce mb-2">📡</div>
          <p class="text-blue-400 font-bold">正在扫描环境 WiFi...</p>
          <p class="text-xs text-gray-500 mt-1">数据将自动写入数据库</p>
        </div>
      </div>

      <table class="w-full text-left text-sm">
        <thead class="bg-gray-800 text-gray-400 uppercase font-mono text-xs tracking-wider cursor-pointer select-none">
          <tr>
            <th @click="sort('ssid')" class="p-4 hover:text-white">SSID (名称) {{ sortIcon('ssid') }}</th>
            <th @click="sort('bssid')" class="p-4 hover:text-white">BSSID (MAC) {{ sortIcon('bssid') }}</th>
            <th @click="sort('channel')" class="p-4 hover:text-white">信道 {{ sortIcon('channel') }}</th>
            <th @click="sort('encryption')" class="p-4 hover:text-white">加密 {{ sortIcon('encryption') }}</th>
            <th @click="sort('client_count')" class="p-4 hover:text-white text-green-400">在线终端 {{ sortIcon('client_count') }}</th>
            <th @click="sort('signal_dbm')" class="p-4 hover:text-white">信号质量 {{ sortIcon('signal_dbm') }}</th>
            <th class="p-4 text-right cursor-default">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-700/50">
          <tr v-if="sortedNetworks.length === 0" class="text-center text-gray-500">
            <td colspan="7" class="p-12">
              暂无数据，请确认 Agent 在线并点击“执行扫描”
            </td>
          </tr>
          
          <tr v-for="(net, index) in sortedNetworks" :key="index" class="hover:bg-gray-800/50 transition group">
            
            <td class="p-4">
              <div class="font-bold text-white">{{ net.ssid }}</div>
            </td>
            
            <td class="p-4 font-mono text-xs text-gray-400">{{ net.bssid }}</td>
            
            <td class="p-4">
              <div class="flex items-center gap-2">
                <span class="font-bold text-gray-300">{{ net.channel }}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded border" :class="net.channel > 14 ? 'border-purple-500 text-purple-400' : 'border-blue-500 text-blue-400'">
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
                <span>{{ net.client_count }} 台设备</span>
                <span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              </div>
              <span v-else class="text-gray-600 text-xs">-</span>
            </td>

            <td class="p-4">
              <div class="flex items-center gap-2">
                <div class="w-16 bg-gray-700 rounded-full h-1.5 overflow-hidden">
                  <div class="h-full transition-all duration-500" :class="getSignalColor(net.signal_dbm)" :style="{ width: getSignalPercent(net.signal_dbm) + '%' }"></div>
                </div>
                <span class="text-xs font-mono w-8 text-right">{{ getSignalPercent(net.signal_dbm) }}%</span>
              </div>
            </td>

            <td class="p-4 text-right">
              <div class="flex justify-end gap-2">
                <button 
                  v-if="monitoringBSSID === net.bssid"
                  class="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 text-white rounded text-xs animate-pulse shadow-lg"
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
                  class="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded text-xs font-bold shadow-lg" 
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
              <span class="animate-pulse">🔴</span> 实时捕获中
            </h3>
            <div class="text-xs text-gray-400 font-mono mt-1">目标: {{ monitoringBSSID }}</div>
          </div>
          <button @click="stopMonitor" class="text-gray-400 hover:text-white">✕</button>
        </div>

        <div class="p-4 overflow-y-auto flex-1 space-y-2 custom-scrollbar">
          <div v-if="monitoredClients.length === 0" class="text-center text-gray-500 py-4 text-xs">
            等待数据回传 (约5秒)...<br>如果没有数据，说明当前没有设备通信。
          </div>

          <div v-for="client in monitoredClients" :key="client.client_mac" class="bg-black/20 p-3 rounded border border-gray-700/50 flex justify-between items-center animate-fade-in">
            <div>
              <div class="text-blue-300 font-mono font-bold text-sm">{{ client.client_mac }}</div>
              <div class="text-[10px] text-gray-500 mt-0.5">最后活跃: {{ formatTime(client.last_seen) }}</div>
            </div>
            <div class="text-right">
              <div class="text-green-400 text-xs font-bold font-mono">{{ client.packet_count }} Pkts</div>
              <div class="text-gray-500 text-xs font-mono">{{ client.signal_dbm }} dBm</div>
            </div>
          </div>
        </div>
      </div>
    </transition>

  </div>
</template>

<script>
import api from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

export default {
  name: "WiFiPanel",
  data() {
    return {
      isScanning: false,
      isDeploying: false,
      selectedInterface: "",
      interfaces: [],
      networks: [],
      
      currentTask: 'idle',
      monitoringBSSID: null,
      monitoredClients: [],
      
      pollTimer: null,
      sortKey: 'signal_dbm',
      sortDesc: true
    };
  },
  computed: {
    hasAgent() { 
      return this.interfaces.length > 0 && this.interfaces[0].name !== 'waiting'; 
    },
    agentStatusText() {
      if (!this.hasAgent) return '离线 / 等待连接...';
      return '在线 (Online)';
    },
    sortedNetworks() {
      return this.networks.slice().sort((a, b) => {
        let valA = a[this.sortKey];
        let valB = b[this.sortKey];
        let modifier = this.sortDesc ? -1 : 1;
        
        if (typeof valA === 'string') return valA.localeCompare(valB) * modifier;
        return (valA - valB) * modifier;
      });
    }
  },
  mounted() {
    this.fetchInterfaces();
    this.loadNetworks();
    
    // 全局轮询器 (3秒一次)
    this.pollTimer = setInterval(() => {
      if (!this.isScanning) {
        this.fetchInterfaces();
        this.loadNetworks(); // 持续从数据库拉取最新数据
      }
      if (this.monitoringBSSID) {
        this.fetchClients();
      }
    }, 3000);
  },
  beforeUnmount() {
    if (this.pollTimer) clearInterval(this.pollTimer);
  },
  methods: {
    // === 排序逻辑 ===
    sort(key) {
      if (this.sortKey === key) this.sortDesc = !this.sortDesc;
      else { this.sortKey = key; this.sortDesc = true; }
    },
    sortIcon(key) {
      if (this.sortKey !== key) return '';
      return this.sortDesc ? '↓' : '↑';
    },

    // === 数据获取 ===
    async fetchInterfaces() {
      try {
        const res = await api.get('/wifi/interfaces');
        this.interfaces = res.data.interfaces || [];
        if (!this.selectedInterface && this.hasAgent) this.selectedInterface = this.interfaces[0].name;
      } catch {}
    },
    
    async loadNetworks() {
      if (this.currentTask === 'idle') {
        const res = await api.get('/wifi/networks');
        if(res.data) this.networks = res.data;
      }
    },

    // === 关键操作 ===
    async deployAgent() {
      this.isDeploying = true;
      try {
        const res = await api.post('/wifi/agent/deploy');
        if (res.data.status === 'success') {
          ElMessage.success(res.data.message);
          this.fetchInterfaces();
        } else {
          ElMessageBox.alert(res.data.message, '部署失败', { type: 'error' });
        }
      } catch (e) {
        ElMessage.error("请求失败: " + e.message);
      } finally {
        this.isDeploying = false;
      }
    },

    async startScan() {
      if (!this.selectedInterface) return ElMessage.warning("请先选择网卡");
      
      this.isScanning = true;
      this.networks = []; 
      
      try {
        const res = await api.post('/wifi/scan/start', { interface: this.selectedInterface });
        if (res.data.status === 'success') {
            await this.loadNetworks(); 
            this.sortKey = 'client_count'; // 扫描完默认按人数排序
            this.sortDesc = true;
        } else {
            ElMessage.error("扫描失败: " + (res.data.message || '超时'));
        }
      } catch (e) {
        ElMessage.error("请求错误");
      } finally {
        this.isScanning = false;
        this.currentTask = 'idle';
      }
    },
    
    async startMonitor(net) {
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
        ElMessage.error("指令下发失败");
        this.stopMonitor();
      }
    },

    async stopMonitor() {
      this.monitoringBSSID = null;
      this.currentTask = 'idle';
      try { await api.post('/wifi/monitor/stop'); } catch (e) {}
    },

    async fetchClients() {
      if (!this.monitoringBSSID) return;
      try {
        const res = await api.get(`/wifi/monitor/clients/${this.monitoringBSSID}`);
        if (res.data) this.monitoredClients = res.data;
      } catch (e) {}
    },

    // === 工具函数 ===
    getBandClass(channel) {
      return channel > 14 ? 'border-purple-500 text-purple-400 bg-purple-900/20' : 'border-blue-500 text-blue-400 bg-blue-900/20';
    },
    getEncClass(enc) {
      if (!enc) return '';
      enc = enc.trim();
      if (enc === 'OPEN') return 'border-red-500 text-red-400 bg-red-900/20';
      if (enc.includes('WPA2')) return 'border-green-500/30 text-green-400 bg-green-900/10';
      return 'border-gray-600 text-gray-400';
    },
    getSignalPercent(sig) { 
      const dbm = parseInt(sig);
      if (dbm <= -100) return 0;
      if (dbm >= -30) return 100;
      return Math.round((dbm + 100) * 1.42); 
    },
    getSignalColor(sig) {
      const p = this.getSignalPercent(sig);
      if (p > 75) return 'bg-green-500';
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
.slide-up-enter-active, .slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from, .slide-up-leave-to { transform: translateY(100%); opacity: 0; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
</style>