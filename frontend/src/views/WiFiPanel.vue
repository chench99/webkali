<template>
  <div class="wifi-container p-6 bg-gray-900 text-white min-h-screen font-mono">
    <div class="panel-header flex justify-between items-end mb-6 border-b border-gray-700 pb-4">
      <div>
        <h2 class="text-2xl font-bold flex items-center gap-3 text-blue-400">
          <span class="text-3xl">🐉</span> Kali 无线渗透 C2 控制台
        </h2>
        <div class="text-gray-500 text-xs mt-1">
          状态: {{ hasAgent ? 'Agent 在线' : '等待连接...' }} | 任务: {{ taskName }}
        </div>
      </div>
    </div>

    <div class="toolbar flex gap-4 justify-between items-center mb-4 bg-gray-800 p-3 rounded border border-gray-700">
      <div class="flex items-center gap-2">
        <span class="text-sm font-bold">选择网卡:</span>
        <select v-model="selectedInterface" class="bg-gray-900 border border-gray-600 px-2 py-1 rounded text-sm w-48" :disabled="isScanning">
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
        {{ isScanning ? '正在扫描 (等待回传)...' : '开始普通扫描' }}
      </button>
    </div>

    <div class="network-list bg-gray-800 rounded-lg shadow-xl overflow-hidden border border-gray-700">
      <table class="w-full text-left text-sm">
        <thead class="bg-gray-900 text-gray-400 uppercase">
          <tr>
            <th class="p-4">ESSID</th>
            <th class="p-4">BSSID</th>
            <th class="p-4">信道</th>
            <th class="p-4">加密</th>
            <th class="p-4 font-bold text-green-400">在线终端</th>
            <th class="p-4">信号</th>
            <th class="p-4 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-700">
          <tr v-if="networks.length === 0" class="text-center text-gray-500">
            <td colspan="7" class="p-8">暂无数据，请先执行扫描</td>
          </tr>
          <tr v-for="(net, index) in networks" :key="index" class="hover:bg-gray-700 transition group">
            <td class="p-4 font-bold text-white">{{ net.ssid }}</td>
            <td class="p-4 font-mono text-xs text-gray-400">{{ net.bssid }}</td>
            <td class="p-4">{{ net.channel }} <span class="text-xs text-gray-500">({{ net.band }})</span></td>
            
            <td class="p-4">
               <span class="px-2 py-0.5 rounded text-xs border" :class="getEncClass(net.encryption)">
                 {{ net.encryption }}
               </span>
            </td>

            <td class="p-4 font-mono">
              <span v-if="net.clientCount > 0" class="text-green-400 font-bold flex items-center gap-2">
                {{ net.clientCount }} 
                <span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              </span>
              <span v-else class="text-gray-600">-</span>
            </td>

            <td class="p-4">
              <div class="flex items-center gap-2">
                <div class="w-16 bg-gray-900 rounded-full h-1.5 overflow-hidden">
                  <div class="h-full" :class="getSignalColor(net.signal)" :style="{ width: getSignalPercent(net.signal) + '%' }"></div>
                </div>
                <span class="text-xs">{{ net.signal }}</span>
              </div>
            </td>

            <td class="p-4 text-right">
              <button @click="$router.push({ name: 'AttackDetail', params: { bssid: net.bssid } })" class="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded text-xs">
                攻击详情
              </button>
            </td>
          </tr>
        </tbody>
      </table>
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
      pollTimer: null
    };
  },
  computed: {
    hasAgent() {
      return this.interfaces.length > 0 && this.interfaces[0].name !== 'waiting';
    },
    taskName() {
      return this.currentTask === 'idle' ? '空闲' : this.currentTask;
    }
  },
  mounted() {
    this.fetchInterfaces();
    this.fetchNetworks();
    this.pollTimer = setInterval(() => {
        if (!this.isScanning) this.fetchInterfaces();
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
          if (!this.selectedInterface && this.hasAgent) {
             this.selectedInterface = this.interfaces[0].name;
          }
        }
      } catch (e) {}
    },
    async fetchNetworks() {
        try {
            const res = await axios.get('/api/v1/wifi/networks');
            if(res.data) this.networks = res.data;
        } catch(e) {}
    },
    async startScan() {
      if (!this.selectedInterface) return alert("请先选择网卡");
      
      this.isScanning = true;
      this.networks = []; // 清空列表以显示加载感

      try {
        // 请求后端，后端会挂起等待 Agent 回调
        const res = await axios.post('/api/v1/wifi/scan/start', { 
            interface: this.selectedInterface 
        });
        
        if (res.data.status === 'success') {
            this.networks = res.data.networks;
            this.$message?.success(`扫描完成，发现 ${this.networks.length} 个目标`);
        } else {
            this.$message?.error("扫描超时，请检查 Agent 是否掉线");
        }
      } catch (e) {
        alert("请求失败: " + e.message);
      } finally {
        this.isScanning = false;
      }
    },
    getEncClass(enc) {
      if (!enc) return '';
      if (enc.includes('OPEN')) return 'border-red-500 text-red-400 bg-red-900/20';
      return 'border-blue-600 text-blue-400 bg-blue-900/10';
    },
    getSignalPercent(sig) {
      return Math.min(100, Math.max(0, (parseInt(sig) + 100) * 2));
    },
    getSignalColor(sig) {
      const p = this.getSignalPercent(sig);
      return p > 70 ? 'bg-green-500' : p > 40 ? 'bg-yellow-500' : 'bg-red-500';
    }
  }
};
</script>