<template>
  <div class="wifi-container p-6 bg-[#0b1120] text-gray-200 min-h-screen font-sans">
    
    <div class="flex justify-between items-end mb-6 border-b border-gray-800 pb-4">
      <div>
        <h2 class="text-2xl font-bold flex items-center gap-3 text-blue-400">
          <span class="text-3xl">📡</span> 无线渗透控制台
          <span class="text-xs border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 rounded text-blue-300">Persistence Mode</span>
        </h2>
        <div class="text-gray-500 text-xs mt-2 flex gap-4 font-mono">
          <span>Agent: <span :class="hasAgent ? 'text-green-400':'text-red-400'">{{ agentStatusText }}</span></span>
          <span>Task: <span class="text-yellow-400">{{ currentTask }}</span></span>
        </div>
      </div>
      <button v-if="!hasAgent" @click="deployAgent" :disabled="isDeploying" class="bg-red-900/30 hover:bg-red-900/50 border border-red-700 text-red-300 px-4 py-2 rounded text-xs transition">
        {{ isDeploying ? '部署中...' : '🛠️ 部署 Agent' }}
      </button>
    </div>

    <div class="flex gap-4 justify-between items-center mb-6 bg-[#111827] p-4 rounded-xl border border-gray-700/50 shadow-lg">
      <div class="flex items-center gap-3">
        <select v-model="selectedInterface" class="bg-gray-800 border border-gray-600 px-3 py-1.5 rounded text-sm w-56">
          <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">{{ iface.display }}</option>
        </select>
        <button @click="fetchInterfaces" class="text-gray-400 hover:text-white px-2">↻</button>
      </div>
      <button class="px-6 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm shadow-lg transition disabled:opacity-50"
        :disabled="isScanning || !hasAgent" @click="startScan">
        <span v-if="isScanning" class="animate-spin mr-1">⏳</span>
        {{ isScanning ? '扫描中...' : '执行全网扫描' }}
      </button>
    </div>

    <div class="bg-[#111827] rounded-xl shadow-xl overflow-hidden border border-gray-700/50 relative">
      <table class="w-full text-left text-sm">
        <thead class="bg-gray-800 text-gray-400 uppercase font-mono text-xs cursor-pointer select-none">
          <tr>
            <th @click="sort('ssid')" class="p-4 hover:text-white">SSID {{ sortIcon('ssid') }}</th>
            <th @click="sort('bssid')" class="p-4 hover:text-white">BSSID {{ sortIcon('bssid') }}</th>
            <th @click="sort('channel')" class="p-4 hover:text-white">CH {{ sortIcon('channel') }}</th>
            <th @click="sort('encryption')" class="p-4 hover:text-white">ENC {{ sortIcon('encryption') }}</th>
            <th @click="sort('client_count')" class="p-4 hover:text-white text-green-400">Clients {{ sortIcon('client_count') }}</th>
            <th @click="sort('signal_dbm')" class="p-4 hover:text-white">Signal {{ sortIcon('signal_dbm') }}</th>
            <th class="p-4 text-right">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-700/50">
          <tr v-for="net in sortedNetworks" :key="net.bssid" class="hover:bg-gray-800/50 transition group">
            <td class="p-4 font-bold text-white">{{ net.ssid }}</td>
            <td class="p-4 font-mono text-xs text-gray-400">{{ net.bssid }}</td>
            <td class="p-4">
              <span class="px-1 rounded border text-[10px]" :class="net.channel > 14 ? 'border-purple-500 text-purple-400' : 'border-blue-500 text-blue-400'">
                {{ net.channel > 14 ? '5G' : '2.4G' }}
              </span>
              <span class="ml-1 font-bold">{{ net.channel }}</span>
            </td>
            <td class="p-4 text-xs">{{ net.encryption }}</td>
            <td class="p-4 font-mono text-green-400 font-bold">
              {{ net.client_count > 0 ? net.client_count : '-' }}
            </td>
            <td class="p-4">
              <div class="flex items-center gap-2">
                <div class="w-16 bg-gray-700 rounded-full h-1.5 overflow-hidden">
                  <div class="h-full transition-all duration-500" :class="getSignalColor(net.signal_dbm)" :style="{ width: getSignalPercent(net.signal_dbm) + '%' }"></div>
                </div>
                <span class="text-xs font-mono w-8 text-right">{{ getSignalPercent(net.signal_dbm) }}%</span>
              </div>
            </td>
            <td class="p-4 text-right flex justify-end gap-2">
              <button v-if="monitoringBSSID === net.bssid" @click="stopMonitor" class="text-yellow-400 border border-yellow-400 px-2 py-1 rounded text-xs animate-pulse">停止</button>
              <button v-else @click="startMonitor(net)" class="text-gray-300 border border-gray-600 px-2 py-1 rounded text-xs hover:bg-gray-700">监听</button>
              <button @click="$router.push(`/wifi/attack/${net.bssid}`)" class="bg-red-600 text-white px-3 py-1 rounded text-xs hover:bg-red-500">攻击</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <transition name="slide-up">
      <div v-if="monitoringBSSID" class="fixed bottom-6 right-6 w-80 bg-[#1f2937] border border-yellow-500/30 rounded-lg shadow-2xl p-4 z-50">
        <div class="flex justify-between border-b border-gray-700 pb-2 mb-2">
          <span class="text-yellow-500 font-bold text-sm flex items-center gap-2"><span class="animate-pulse">●</span> 实时监听: {{ monitoringBSSID }}</span>
          <button @click="stopMonitor" class="text-gray-400 hover:text-white">✕</button>
        </div>
        <div class="max-h-60 overflow-y-auto space-y-2 custom-scrollbar">
          <div v-if="monitoredClients.length === 0" class="text-center text-xs text-gray-500 py-4">等待数据回传...</div>
          <div v-for="client in monitoredClients" :key="client.client_mac" class="flex justify-between items-center text-xs bg-black/20 p-2 rounded border border-gray-700/50">
            <div>
              <div class="text-blue-300 font-mono font-bold">{{ client.client_mac }}</div>
              <div class="text-gray-500 text-[10px] mt-0.5">Last Seen: {{ formatTime(client.last_seen) }}</div>
            </div>
            <div class="text-right">
              <div class="text-green-400 font-bold">{{ client.packet_count }} Pkts</div>
              <div class="text-gray-500">{{ client.signal_dbm }} dBm</div>
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
  data() {
    return {
      isScanning: false,
      isDeploying: false,
      selectedInterface: "",
      interfaces: [],
      networks: [],
      monitoringBSSID: null,
      monitoredClients: [],
      pollTimer: null,
      sortKey: 'signal_dbm',
      sortDesc: true,
      currentTask: 'idle'
    };
  },
  computed: {
    hasAgent() { return this.interfaces.length > 0 && this.interfaces[0].name !== 'waiting'; },
    agentStatusText() { return this.hasAgent ? 'ONLINE' : 'OFFLINE'; },
    sortedNetworks() {
      return this.networks.slice().sort((a, b) => {
        let valA = a[this.sortKey], valB = b[this.sortKey];
        if (typeof valA === 'string') return this.sortDesc ? valB.localeCompare(valA) : valA.localeCompare(valB);
        return this.sortDesc ? valB - valA : valA - valB;
      });
    }
  },
  mounted() {
    this.fetchInterfaces();
    this.loadNetworks(); // 初始加载
    this.pollTimer = setInterval(() => {
      if (!this.isScanning) {
        this.fetchInterfaces();
        this.loadNetworks(); // 持续轮询数据库
      }
      if (this.monitoringBSSID) this.fetchClients();
    }, 3000);
  },
  beforeUnmount() { clearInterval(this.pollTimer); },
  methods: {
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
    async deployAgent() {
      this.isDeploying = true;
      try {
        const res = await api.post('/wifi/agent/deploy');
        res.data.status === 'success' ? ElMessage.success(res.data.message) : ElMessageBox.alert(res.data.message, 'Error', {type:'error'});
      } catch(e) { ElMessage.error(e.message); }
      finally { this.isDeploying = false; }
    },
    async startScan() {
      if (!this.selectedInterface) return ElMessage.warning("请选择网卡");
      this.isScanning = true;
      this.networks = []; // 视觉清空
      try {
        const res = await api.post('/wifi/scan/start', { interface: this.selectedInterface });
        if (res.data.status === 'success') {
          await this.loadNetworks(); // 扫描完立即加载
          this.sortKey = 'client_count'; // 默认按人数排
        } else ElMessage.error(res.data.message);
      } catch(e) { ElMessage.error("扫描失败"); }
      finally { this.isScanning = false; this.currentTask = 'idle'; }
    },
    async startMonitor(net) {
      this.monitoringBSSID = net.bssid;
      this.currentTask = 'monitor';
      this.monitoredClients = [];
      await api.post('/wifi/monitor/start', { bssid: net.bssid, channel: net.channel, interface: this.selectedInterface });
    },
    async stopMonitor() {
      this.monitoringBSSID = null;
      this.currentTask = 'idle';
      await api.post('/wifi/monitor/stop');
    },
    async fetchClients() {
      const res = await api.get(`/wifi/monitor/clients/${this.monitoringBSSID}`);
      if(res.data) this.monitoredClients = res.data;
    },
    // 工具函数
    sort(key) {
      if (this.sortKey === key) this.sortDesc = !this.sortDesc;
      else { this.sortKey = key; this.sortDesc = true; }
    },
    sortIcon(key) { return this.sortKey !== key ? '' : (this.sortDesc ? '↓' : '↑'); },
    getSignalPercent(dbm) { return Math.min(Math.max(Math.round((dbm + 100) * 1.42), 0), 100); },
    getSignalColor(dbm) {
      const p = this.getSignalPercent(dbm);
      return p > 70 ? 'bg-green-500' : p > 40 ? 'bg-yellow-500' : 'bg-red-500';
    },
    formatTime(t) { return new Date(t).toLocaleTimeString(); }
  }
};
</script>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from, .slide-up-leave-to { transform: translateY(100%); opacity: 0; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
</style>