<template>
  <div class="wifi-container p-6 bg-gray-900 text-white min-h-screen font-mono">
    
    <div class="panel-header flex justify-between items-end mb-6 border-b border-gray-700 pb-4">
      <div>
        <h2 class="text-2xl font-bold flex items-center gap-3 text-blue-400">
          <span class="text-3xl">🐉</span> Kali 无线渗透 C2 控制台 <span class="text-xs border px-2 rounded">v2.0 Pro</span>
        </h2>
        <div class="text-gray-500 text-xs mt-1">
          状态: <span :class="hasAgent ? 'text-green-400':'text-red-400'">{{ hasAgent ? 'ONLINE' : 'OFFLINE' }}</span> | 
          当前任务: <span class="text-yellow-400">{{ taskName }}</span>
        </div>
      </div>
    </div>

    <div class="toolbar flex gap-4 justify-between items-center mb-4 bg-gray-800 p-3 rounded border border-gray-700">
      <div class="flex items-center gap-2">
        <span class="text-sm font-bold">监听接口:</span>
        <select v-model="selectedInterface" class="bg-gray-900 border border-gray-600 px-2 py-1 rounded text-sm w-48">
          <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
            {{ iface.display }}
          </option>
        </select>
        <button @click="fetchInterfaces" class="text-gray-400 hover:text-white px-2">↻</button>
      </div>

      <button 
        class="px-6 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed transition font-bold flex items-center gap-2"
        :disabled="isScanning || !hasAgent || currentTask !== 'idle'"
        @click="startScan"
      >
        <span v-if="isScanning" class="animate-spin">⏳</span>
        {{ isScanning ? '正在扫描 (2.4G/5G)...' : '执行全频段扫描' }}
      </button>
    </div>

    <div class="network-list bg-gray-800 rounded-lg shadow-xl overflow-hidden border border-gray-700 mb-6">
      <table class="w-full text-left text-sm">
        <thead class="bg-gray-900 text-gray-400 uppercase">
          <tr>
            <th class="p-4">ESSID</th>
            <th class="p-4">BSSID</th>
            <th class="p-4">信道 / 频段</th>
            <th class="p-4">加密</th>
            <th class="p-4 font-bold text-green-400">在线终端 (概览)</th>
            <th class="p-4">信号</th>
            <th class="p-4 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-700">
          <tr v-if="networks.length === 0" class="text-center text-gray-500">
            <td colspan="7" class="p-8">暂无数据，请选择网卡并开始扫描</td>
          </tr>
          
          <tr v-for="(net, index) in networks" :key="index" class="hover:bg-gray-700 transition group">
            <td class="p-4 font-bold text-white">{{ net.ssid }}</td>
            <td class="p-4 font-mono text-xs text-gray-400">{{ net.bssid }}</td>
            
            <td class="p-4">
              <div class="flex flex-col">
                <span class="font-bold">CH {{ net.channel }}</span>
                <span class="text-[10px] px-1 rounded w-fit" :class="getBandClass(net.band, net.channel)">
                  {{ net.band || (net.channel > 14 ? '5G' : '2.4G') }}
                </span>
              </div>
            </td>
            
            <td class="p-4">
              <span class="px-2 py-0.5 rounded text-xs border" :class="getEncClass(net.encryption)">
                {{ net.encryption }}
              </span>
            </td>

            <td class="p-4 font-mono">
              <span v-if="net.clientCount > 0" class="text-green-400 font-bold flex items-center gap-2">
                {{ net.clientCount }} Users
                <span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              </span>
              <span v-else class="text-gray-600">-</span>
            </td>

            <td class="p-4">
              <div class="flex items-center gap-2">
                <div class="w-16 bg-gray-900 rounded-full h-1.5 overflow-hidden">
                  <div class="h-full transition-all" :class="getSignalColor(net.signal)" :style="{ width: getSignalPercent(net.signal) + '%' }"></div>
                </div>
                <span class="text-xs">{{ net.signal }}</span>
              </div>
            </td>

            <td class="p-4 text-right flex justify-end gap-2">
              <button 
                v-if="monitoringBSSID === net.bssid"
                class="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 text-white rounded text-xs animate-pulse"
                @click="stopMonitor"
              >
                停止监听
              </button>
              <button 
                v-else
                class="px-3 py-1 bg-gray-600 hover:bg-gray-500 text-white rounded text-xs border border-gray-500"
                @click="startMonitor(net)"
                :disabled="currentTask !== 'idle'"
              >
                查看监听
              </button>
              
              <button class="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded text-xs" @click="$router.push({ name: 'AttackDetail', params: { bssid: net.bssid } })">
                攻击
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="monitoringBSSID && monitoredClients.length > 0" class="bg-gray-800 border border-yellow-600/50 rounded-lg p-4 shadow-2xl animate-fade-in-up">
      <div class="flex justify-between items-center mb-3 border-b border-gray-700 pb-2">
        <h3 class="font-bold text-yellow-500 flex items-center gap-2">
          <span>📡</span> 实时捕获客户端 (Target: {{ monitoringBSSID }})
        </h3>
        <span class="text-xs text-gray-400">Auto Refreshing...</span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-60 overflow-y-auto">
        <div v-for="client in monitoredClients" :key="client.client_mac" class="bg-gray-900 p-3 rounded border border-gray-700 flex justify-between items-center">
          <div>
            <div class="text-blue-300 font-mono font-bold">{{ client.client_mac }}</div>
            <div class="text-xs text-gray-500 mt-1">Last Seen: {{ new Date(client.last_seen).toLocaleTimeString() }}</div>
          </div>
          <div class="text-right">
            <div class="text-green-400 text-xs font-bold">{{ client.packet_count }} pkts</div>
            <div class="text-gray-400 text-xs">{{ client.signal }} dBm</div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script>
import axios from 'axios';

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
      pollTimer: null
    };
  },
  computed: {
    hasAgent() { return this.interfaces.length > 0 && this.interfaces[0].name !== 'waiting'; },
    taskName() { return this.currentTask === 'idle' ? '空闲' : this.currentTask; }
  },
  mounted() {
    this.fetchInterfaces();
    this.fetchNetworks();
    
    // 全局轮询 (状态 + 监听数据)
    this.pollTimer = setInterval(() => {
      if (!this.isScanning) {
        this.fetchInterfaces(); // 检查掉线
      }
      if (this.monitoringBSSID) {
        this.fetchMonitoredClients(); // 如果正在监听，拉取数据库
      }
    }, 3000);
  },
  beforeDestroy() {
    if (this.pollTimer) clearInterval(this.pollTimer);
  },
  methods: {
    async fetchInterfaces() {
      try {
        const res = await axios.get('/api/v1/wifi/interfaces');
        if (res.data.interfaces) {
          this.interfaces = res.data.interfaces;
          if (!this.selectedInterface && this.hasAgent) this.selectedInterface = this.interfaces[0].name;
        }
      } catch (e) {}
    },
    async fetchNetworks() {
       // 空闲时才允许更新列表
       if (this.currentTask === 'idle') {
           try {
               const res = await axios.get('/api/v1/wifi/networks');
               if(res.data) this.networks = res.data;
           } catch(e) {}
       }
    },
    async startScan() {
      if (!this.selectedInterface) return alert("请先选择网卡");
      this.isScanning = true;
      this.networks = []; 

      try {
        const res = await axios.post('/api/v1/wifi/scan/start', { interface: this.selectedInterface });
        if (res.data.status === 'success') {
            this.networks = res.data.networks;
            this.$message?.success(`扫描完成，覆盖 5G 频段`);
        } else {
            this.$message?.error("扫描超时");
        }
      } catch (e) {
        alert("错误: " + e.message);
      } finally {
        this.isScanning = false;
      }
    },
    
    // [交互] 开始监听
    async startMonitor(net) {
      this.monitoringBSSID = net.bssid;
      this.currentTask = 'monitor_target';
      this.monitoredClients = []; // 清空旧数据
      
      try {
        await axios.post('/api/v1/wifi/monitor/start', {
          bssid: net.bssid,
          channel: net.channel
        });
        this.$message?.success(`已锁定信道 ${net.channel}，开始捕获客户端...`);
      } catch (e) {
        this.stopMonitor();
      }
    },

    // [交互] 停止监听
    async stopMonitor() {
      await axios.post('/api/v1/wifi/monitor/stop');
      this.currentTask = 'idle';
      this.monitoringBSSID = null;
    },

    // [数据] 从数据库拉取定向监听结果
    async fetchMonitoredClients() {
      if (!this.monitoringBSSID) return;
      try {
        const res = await axios.get(`/api/v1/wifi/monitor/clients/${this.monitoringBSSID}`);
        if (res.data) {
          this.monitoredClients = res.data.sort((a,b) => b.last_seen.localeCompare(a.last_seen));
        }
      } catch (e) {}
    },

    // === 样式辅助 ===
    getBandClass(band, channel) {
      if (band === '5G' || channel > 14) return 'bg-purple-900/40 text-purple-300 border-purple-500/50';
      return 'bg-blue-900/40 text-blue-300 border-blue-500/50';
    },
    getEncClass(enc) {
      if (!enc) return '';
      if (enc.includes('OPEN')) return 'border-red-500 text-red-400 bg-red-900/20';
      return 'border-gray-600 text-gray-400';
    },
    getSignalPercent(sig) { return Math.min(100, Math.max(0, (parseInt(sig) + 100) * 2)); },
    getSignalColor(sig) {
      const p = this.getSignalPercent(sig);
      return p > 70 ? 'bg-green-500' : p > 40 ? 'bg-yellow-500' : 'bg-red-500';
    }
  }
};
</script>

<style scoped>
.animate-fade-in-up { animation: fadeInUp 0.5s ease-out; }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
</style>