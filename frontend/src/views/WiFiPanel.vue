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
          <span v-if="monitoringBSSID" class="text-yellow-400 animate-pulse">正在监听: {{ monitoringBSSID }}</span>
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
            <th @click="handleSort('ssid')" class="p-4 cursor-pointer hover:text-white transition group select-none">
              SSID (名称) <span class="ml-1 opacity-0 group-hover:opacity-50">{{ sortIcon('ssid') }}</span>
            </th>
            <th @click="handleSort('bssid')" class="p-4 cursor-pointer hover:text-white transition group select-none">
              BSSID (MAC) <span class="ml-1 opacity-0 group-hover:opacity-50">{{ sortIcon('bssid') }}</span>
            </th>
            <th @click="handleSort('channel')" class="p-4 cursor-pointer hover:text-white transition group select-none">
              信道/频段 <span class="ml-1 opacity-0 group-hover:opacity-50">{{ sortIcon('channel') }}</span>
            </th>
            <th @click="handleSort('encryption')" class="p-4 cursor-pointer hover:text-white transition group select-none">
              加密 <span class="ml-1 opacity-0 group-hover:opacity-50">{{ sortIcon('encryption') }}</span>
            </th>
            <th @click="handleSort('client_count')" class="p-4 cursor-pointer hover:text-white transition group select-none text-green-400">
              在线客户端 <span class="ml-1 opacity-0 group-hover:opacity-50">{{ sortIcon('client_count') }}</span>
            </th>
            <th @click="handleSort('signal')" class="p-4 cursor-pointer hover:text-white transition group select-none">
              信号质量 <span class="ml-1 opacity-0 group-hover:opacity-50">{{ sortIcon('signal') }}</span>
            </th>
            <th class="p-4 text-right">操作</th>
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
                  <div 
                    class="h-full transition-all duration-500 ease-out" 
                    :class="getSignalColor(net.signal)" 
                    :style="{ width: getSignalPercent(net.signal) + '%' }"
                  ></div>
                </div>
                <span class="text-xs font-mono w-10 text-right">{{ getSignalPercent(net.signal) }}%</span>
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
      
      // 任务状态
      currentTask: 'idle',
      monitoringBSSID: null,
      monitoredClients: [],
      
      pollTimer: null,

      // 排序状态
      sortKey: 'signal', // 默认按信号排序
      sortDesc: true     // 默认降序 (信号强的在前)
    };
  },
  computed: {
    hasAgent() { 
      return this.interfaces.length > 0 && this.interfaces[0].name !== 'waiting'; 
    },
    agentStatusText() {
      if (!this.hasAgent) return '离线 / 等待连接...';
      return 'ONLINE';
    },
    // 排序逻辑
    sortedNetworks() {
      return this.networks.slice().sort((a, b) => {
        let modifier = this.sortDesc ? -1 : 1;
        
        // 信号特殊处理 (dBm是负数，越接近0越强)
        // 比如 -30 > -90
        if (this.sortKey === 'signal') return (a.signal - b.signal) * modifier;
        
        // 在线人数
        if (this.sortKey === 'client_count') return (a.client_count - b.client_count) * modifier;
        
        // 信道
        if (this.sortKey === 'channel') return (a.channel - b.channel) * modifier;
        
        // 字符串字段
        if (this.sortKey === 'ssid') return a.ssid.localeCompare(b.ssid) * modifier;
        if (this.sortKey === 'bssid') return a.bssid.localeCompare(b.bssid) * modifier;
        if (this.sortKey === 'encryption') return a.encryption.localeCompare(b.encryption) * modifier;
        
        return 0;
      });
    }
  },
  mounted() {
    this.fetchInterfaces();
    this.fetchNetworks(); 
    
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
    // === 排序处理 ===
    handleSort(key) {
      if (this.sortKey === key) {
        this.sortDesc = !this.sortDesc; // 切换顺序
      } else {
        this.sortKey = key;
        this.sortDesc = true; // 默认降序 (数字大在前)
      }
    },
    sortIcon(key) {
      if (this.sortKey !== key) return '↕';
      return this.sortDesc ? '↓' : '↑';
    },

    // === 基础数据 ===
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

    async fetchNetworks() {
       if (this.currentTask === 'idle' && !this.isScanning) {
           try {
               const res = await api.get('/wifi/networks');
               if(res.data) this.networks = res.data;
           } catch(e) {}
       }
    },

    // === 部署逻辑 ===
    async deployAgent() {
      this.isDeploying = true;
      try {
        const res = await api.post('/wifi/agent/deploy');
        if (res.data.status === 'success') {
          ElMessage.success(res.data.message);
          this.fetchInterfaces();
        } else {
          ElMessageBox.alert(res.data.message, '部署失败', {
            type: 'error',
            confirmButtonText: '确定'
          });
        }
      } catch (e) {
        ElMessage.error("请求失败: " + e.message);
      } finally {
        this.isDeploying = false;
      }
    },

    // === 扫描逻辑 ===
    async startScan() {
      if (!this.selectedInterface) return alert("请先选择网卡");
      
      this.isScanning = true;
      this.networks = []; 
      
      try {
        const res = await api.post('/wifi/scan/start', { interface: this.selectedInterface });
        if (res.data.status === 'success') {
            this.networks = res.data.networks;
            // 扫描完成后默认按在线人数排序，更直观
            this.sortKey = 'client_count';
            this.sortDesc = true;
        } else {
            ElMessage.error("扫描失败: " + (res.data.message || '超时'));
        }
      } catch (e) {
        ElMessage.error("请求错误: " + e.message);
      } finally {
        this.isScanning = false;
        this.currentTask = 'idle';
      }
    },
    
    // === 监听逻辑 ===
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
      try {
        await api.post('/wifi/monitor/stop');
      } catch (e) {}
    },

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
      // 将 -100 到 -30 dBm 映射到 0-100%
      // -30dBm = 100%, -100dBm = 0%
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