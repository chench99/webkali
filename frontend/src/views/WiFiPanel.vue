<template>
  <div class="wifi-container p-6 bg-gray-900 text-white min-h-screen font-mono">
    
    <div class="panel-header flex justify-between items-end mb-6 border-b border-gray-700 pb-4">
      <div>
        <h2 class="text-2xl font-bold flex items-center gap-3 text-blue-400">
          <span class="text-3xl">🐉</span> Kali 无线渗透 C2 控制台 <span class="text-sm text-gray-500 font-normal border border-gray-600 px-2 rounded">v5.2 Deep-Audit</span>
        </h2>
        <div class="text-gray-500 text-xs mt-1">
          全自动 SSH 托管 | 零接触部署 | 混合架构 | 深度审计
        </div>
      </div>

      <div class="system-status flex gap-4 text-xs bg-gray-800 px-4 py-2 rounded border border-gray-700 shadow-inner">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
          <span class="text-gray-400">C2 Server:</span>
          <span class="text-green-400">Running</span>
        </div>
        
        <div class="flex items-center gap-2 border-l border-gray-600 pl-4">
          <span class="text-gray-400">Agent:</span>
          <span :class="hasAgent ? 'text-green-400 font-bold' : 'text-red-400 font-bold animate-pulse'">
            {{ hasAgent ? '已连接' : '离线' }}
          </span>
        </div>

        <div class="flex items-center gap-2 border-l border-gray-600 pl-4">
          <span class="text-gray-400">任务:</span>
          <span class="font-bold" :class="currentTask === 'idle' ? 'text-gray-400' : 'text-yellow-400'">{{ taskName }}</span>
        </div>
        
        <div class="flex items-center gap-2 border-l border-gray-600 pl-4">
          <span class="text-gray-400">CPU:</span>
          <span :class="getLoadClass(systemStatus.cpu_percent)">{{ systemStatus.cpu_percent || 0 }}%</span>
        </div>
      </div>
    </div>

    <div class="toolbar flex flex-wrap gap-4 justify-between items-center mb-4 bg-gray-800 p-3 rounded border border-gray-700">
      
      <div class="flex gap-3 items-center">
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-400 font-bold">监听接口:</span>
          <select 
            v-model="selectedInterface" 
            class="bg-gray-900 border border-gray-600 text-white px-3 py-1.5 rounded text-sm focus:border-blue-500 outline-none w-64 font-mono"
            :disabled="isScanning || currentTask !== 'idle'"
          >
            <option value="" disabled>
              {{ hasAgent ? '请选择 Agent 网卡...' : '等待 Agent 上线...' }}
            </option>
            <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
              {{ iface.display || iface.name }}
            </option>
          </select>
          <button @click="fetchInterfaces" title="刷新列表" class="text-gray-400 hover:text-white px-2">↻</button>
        </div>

        <div v-if="!hasAgent" class="text-xs text-red-400 flex items-center gap-2 bg-red-900/20 px-2 py-1 rounded border border-red-900/50">
          <span>❌ 与 Kali 断开连接</span>
        </div>
      </div>

      <div class="search-box relative ml-4 flex-1 max-w-md">
        <span class="absolute left-2 top-1.5 text-gray-500 text-xs">🔍</span>
        <input 
          v-model="searchQuery"
          type="text" 
          placeholder="搜索 SSID / MAC / 厂商..." 
          class="bg-gray-900 border border-gray-600 text-white pl-8 pr-4 py-1.5 rounded focus:outline-none focus:border-blue-500 w-full text-sm"
        >
      </div>

      <div class="controls flex gap-3 items-center">
        <button 
          class="px-4 py-2 rounded bg-purple-700 hover:bg-purple-600 disabled:opacity-50 transition-all shadow-lg flex items-center gap-2 font-bold text-sm border border-purple-500/30"
          :disabled="!hasAgent || (currentTask !== 'idle' && currentTask !== 'deep_scan')"
          @click="toggleDeepScan"
        >
          <span v-if="currentTask === 'deep_scan'" class="animate-spin">🌀</span>
          {{ currentTask === 'deep_scan' ? '停止深度扫描' : '🚀 深度全网扫描' }}
        </button>

        <button 
          class="px-5 py-2 rounded bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 disabled:opacity-50 transition-all shadow-lg flex items-center gap-2 font-bold text-sm"
          :disabled="isScanning || !hasAgent || currentTask !== 'idle'"
          @click="startScan"
        >
          <span v-if="isScanning" class="animate-spin">⏳</span>
          {{ isScanning ? '等待回传...' : '普通扫描 (SCAN)' }}
        </button>
      </div>
    </div>

    <div class="network-list bg-gray-800 rounded-lg shadow-xl overflow-hidden border border-gray-700 mb-6">
      <table class="w-full text-left text-sm">
        <thead class="bg-gray-900 text-gray-400 uppercase tracking-wider">
          <tr>
            <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('ssid')">ESSID ⇅</th>
            <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('bssid')">BSSID ⇅</th>
            <th class="p-4 border-b border-gray-700">厂商</th>
            <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('channel')">信道 ⇅</th>
            <th class="p-4 border-b border-gray-700">加密</th>
            <th class="p-4 border-b border-gray-700 font-bold text-blue-400">在线终端 (Clients)</th>
            <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('signal')">信号 ⇅</th>
            <th class="p-4 border-b border-gray-700">情报</th>
            <th class="p-4 text-right border-b border-gray-700">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-700">
          
          <tr v-if="!hasAgent && !isDeploying">
            <td colspan="9" class="p-16 text-center">
              <div class="flex flex-col items-center gap-4">
                <div class="text-5xl opacity-50">🔌</div>
                <div>
                  <h3 class="text-lg font-bold text-red-400">Agent 未连接</h3>
                  <p class="text-gray-500 text-xs mt-1">Kali 节点未响应心跳，需要重新部署。</p>
                </div>
                <button @click="deployAgent" class="px-6 py-2 bg-green-600 hover:bg-green-500 text-white rounded font-bold transition shadow-lg flex items-center gap-2">
                  <span>📡</span> 一键远程部署 / 重连 Agent
                </button>
              </div>
            </td>
          </tr>

          <tr v-if="isDeploying">
            <td colspan="9" class="p-16 text-center">
              <div class="flex flex-col items-center gap-4 animate-pulse">
                <div class="text-5xl">🚀</div>
                <div><h3 class="text-lg font-bold text-blue-400">正在通过 SSH 部署...</h3></div>
              </div>
            </td>
          </tr>

          <tr v-if="hasAgent && filteredNetworks.length === 0 && !isScanning">
            <td colspan="9" class="p-12 text-center text-gray-500">
              <div class="text-4xl mb-2">📡</div>
              <div>Agent 已就绪，请点击右上角执行扫描</div>
            </td>
          </tr>

          <tr v-for="(net, index) in filteredNetworks" :key="index" class="hover:bg-gray-700 transition-colors group">
            <td class="p-4 font-bold text-white group-hover:text-blue-300">{{ net.ssid || '<Hidden>' }}</td>
            <td class="p-4 text-gray-400 font-mono text-xs select-all">{{ net.bssid }}</td>
            <td class="p-4 text-gray-300 text-xs">{{ net.vendor || 'Unknown' }}</td>
            <td class="p-4"><div class="flex flex-col"><span class="text-white font-bold text-xs">CH {{ net.channel }}</span><span class="text-xs text-gray-500 scale-90 origin-left">{{ net.band || '2.4G' }}</span></div></td>
            <td class="p-4"><span class="px-2 py-0.5 rounded text-xs font-bold border" :class="getEncClass(net.encryption)">{{ net.encryption }}</span></td>
            
            <td class="p-4 text-xs font-mono">
              <div v-if="monitoringBSSID === net.bssid" class="flex items-center gap-2">
                <span class="text-green-400 font-bold text-lg">{{ net.clientCount || 0 }}</span>
                <span class="relative flex h-3 w-3">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                </span>
                <span class="text-green-500 font-bold text-[10px]">MONITORING</span>
              </div>
              <div v-else>
                <button 
                  @click="startTargetMonitor(net)"
                  class="flex items-center gap-1 px-2 py-1 bg-gray-800 border border-gray-600 hover:bg-gray-600 rounded text-gray-400 hover:text-white transition"
                  :disabled="currentTask !== 'idle' && currentTask !== 'monitor_target'"
                  title="锁定此频道，统计实时在线人数"
                >
                  <span>👁️</span> 查看监听
                </button>
              </div>
            </td>

            <td class="p-4"><div class="w-24 bg-gray-900 rounded-full h-1.5 mt-1 overflow-hidden"><div class="h-full transition-all duration-500" :class="getSignalColor(net.signal)" :style="{ width: getSignalPercent(net.signal) + '%' }"></div></div><div class="text-xs text-gray-500 mt-1">{{ net.signal }} dBm</div></td>
            <td class="p-4"><span v-html="getIntelligence(net)"></span></td>
            
            <td class="p-4 text-right flex gap-2 justify-end">
              <button 
                v-if="monitoringBSSID === net.bssid"
                class="px-3 py-1 bg-yellow-600 hover:bg-yellow-500 text-white rounded text-xs"
                @click="stopMonitor"
              >
                停止
              </button>

              <button class="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded text-xs transition-colors shadow hover:shadow-red-500/50 flex items-center gap-1" @click="attackTarget(net)">
                <span>☠️</span> 攻击
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <transition name="slide-fade">
      <div v-if="currentTask === 'deep_scan' || deepScanClients.length > 0" class="deep-scan-panel bg-gray-800 border border-purple-500/30 rounded-lg p-5 shadow-2xl relative overflow-hidden">
        <div class="absolute -right-10 -top-10 w-40 h-40 bg-purple-600/10 rounded-full blur-3xl"></div>
        
        <div class="flex justify-between items-center mb-4 relative z-10">
          <h3 class="font-bold text-lg text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-400 flex items-center gap-2">
            <span v-if="currentTask === 'deep_scan'" class="animate-spin text-purple-400">📡</span>
            全频段深度捕获 (Deep Audit Results)
          </h3>
          <div class="text-xs text-gray-500 font-mono">
            已捕获终端: <span class="text-white font-bold">{{ deepScanClients.length }}</span> | 
            当前信道: <span class="text-purple-400">Hopping...</span>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 max-h-[400px] overflow-y-auto pr-2 scrollbar-thin">
          <div v-for="client in deepScanClients" :key="client.client_mac" class="bg-gray-900/80 p-3 rounded border border-gray-700 hover:border-purple-500 transition group relative">
            <div class="flex justify-between items-start">
              <div class="text-blue-300 font-mono font-bold">{{ client.client_mac }}</div>
              <div class="text-[10px] bg-gray-800 px-1 rounded text-gray-400">{{ client.vendor || 'Unknown' }}</div>
            </div>
            
            <div class="mt-2 text-xs text-gray-400 flex flex-col gap-1">
              <div class="flex items-center gap-1">
                <span>🔗</span> 
                <span :class="client.connected_bssid ? 'text-green-400' : 'text-gray-600'">
                  {{ client.connected_bssid || '未连接 (Not Associated)' }}
                </span>
              </div>
              <div class="flex items-center gap-1">
                <span>📶</span> {{ client.signal }} dBm (CH {{ client.capture_channel }})
              </div>
            </div>

            <div v-if="client.probed_essids" class="mt-2 pt-2 border-t border-gray-700">
              <div class="text-[10px] text-yellow-500 font-bold mb-1">曾经连过 (Probed):</div>
              <div class="flex flex-wrap gap-1">
                <span v-for="ssid in client.probed_essids.split(',')" :key="ssid" class="bg-yellow-900/20 text-yellow-200 text-[10px] px-1.5 rounded border border-yellow-900/50">
                  {{ ssid }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: "WiFiPanel",
  data() {
    return {
      isScanning: false,
      isDeploying: false,
      searchQuery: "",
      selectedInterface: "", 
      interfaces: [], 
      sortKey: 'signal',
      sortOrder: -1,
      networks: [], // 基础 WiFi 列表
      systemStatus: { online_users: 1, cpu_percent: 0 },
      
      // === 新增状态 ===
      currentTask: 'idle', // 'idle', 'monitor_target', 'deep_scan'
      monitoringBSSID: null, // 当前正在监听哪个 BSSID
      deepScanClients: [],   // 深度扫描结果
      pollTimer: null        // 轮询定时器
    };
  },
  computed: {
    hasAgent() {
      return this.interfaces.length > 0 && this.interfaces[0].name !== 'waiting';
    },
    taskName() {
      const map = {
        'idle': '空闲 (Idle)',
        'monitor_target': '定向监听 (Targeting)',
        'deep_scan': '深度审计 (Deep Scan)'
      };
      return map[this.currentTask] || this.currentTask;
    },
    filteredNetworks() {
      let result = this.networks;
      if (this.searchQuery) {
        const q = this.searchQuery.toLowerCase();
        result = result.filter(n => (n.ssid && n.ssid.toLowerCase().includes(q)) || (n.bssid && n.bssid.toLowerCase().includes(q)));
      }
      result = result.sort((a, b) => {
        let valA = a[this.sortKey]; let valB = b[this.sortKey];
        if (typeof valA === 'string') { valA = valA.toLowerCase(); valB = valB.toLowerCase(); }
        if (valA < valB) return -1 * this.sortOrder; if (valA > valB) return 1 * this.sortOrder; return 0;
      });
      return result;
    }
  },
  mounted() {
    this.fetchSystemStatus();
    this.fetchInterfaces(); 
    this.fetchNetworks(); // 初始加载一次列表

    // 启动全局轮询 (3秒一次)
    this.pollTimer = setInterval(() => {
        this.fetchSystemStatus();
        this.pollMonitorData(); // 轮询监听数据
        if (!this.isScanning && !this.isDeploying) this.fetchInterfaces();
    }, 3000);
  },
  beforeDestroy() { 
    if (this.pollTimer) clearInterval(this.pollTimer); 
    // 离开页面时建议停止监听，也可以保留让后台继续跑
    // this.stopMonitor(); 
  },
  methods: {
    // === 基础数据获取 ===
    async fetchSystemStatus() { try { const res = await axios.get('/api/v1/system/status'); if (res.data) this.systemStatus = res.data; } catch (e) {} },
    async fetchInterfaces() {
      try {
        const res = await axios.get('/api/v1/wifi/interfaces');
        if (res.data && res.data.interfaces) {
          const newIfaces = res.data.interfaces;
          if (JSON.stringify(newIfaces) !== JSON.stringify(this.interfaces)) {
             this.interfaces = newIfaces;
             if (this.hasAgent && !this.selectedInterface) {
                 const monitor = this.interfaces.find(i => i.mode === 'Monitor');
                 this.selectedInterface = monitor ? monitor.name : this.interfaces[0].name;
             }
          }
        }
      } catch (error) {}
    },
    async fetchNetworks() {
      // 只有在空闲时才刷新列表，避免干扰
      if (this.currentTask === 'idle') {
          try {
              const res = await axios.get('/api/v1/wifi/networks'); // 假设你有这个接口回显已存WiFi
              if(res.data) this.networks = res.data;
          } catch(e) {}
      }
    },

    // === 部署逻辑 ===
    async deployAgent() {
      this.isDeploying = true;
      try {
        const res = await axios.post('/api/v1/wifi/agent/deploy');
        if (res.data.status === 'success') {
          this.$message?.success("Agent 启动成功！");
          setTimeout(() => { this.fetchInterfaces(); this.isDeploying = false; }, 3000);
        } else {
          alert("部署失败: " + res.data.message);
          this.isDeploying = false;
        }
      } catch (e) { this.isDeploying = false; }
    },

    // === 普通扫描 ===
    async startScan() {
      if (!this.selectedInterface) return alert("请先选择 Kali 网卡！");
      this.isScanning = true;
      try {
        const payload = { interface: this.selectedInterface };
        const res = await axios.post('/api/v1/wifi/scan/start', payload);
        if (res.data.status === 'timeout') this.$message?.error("扫描超时");
        else {
            if (res.data.networks) this.networks = res.data.networks;
            this.$message?.success(`更新 ${this.networks.length} 个目标`);
        }
      } catch (e) { alert("Error: " + e.message); } 
      finally { this.isScanning = false; }
    },
    
    // === 🚀 新增功能：定向监听 ===
    async startTargetMonitor(net) {
      // 1. 如果正在做别的任务，先停止
      if (this.currentTask !== 'idle') await this.stopMonitor();

      this.monitoringBSSID = net.bssid;
      this.currentTask = 'monitor_target';
      
      try {
        await axios.post('/api/v1/wifi/monitor/start', {
          bssid: net.bssid,
          channel: net.channel
        });
        this.$message?.success(`锁定监听 ${net.ssid} (CH ${net.channel})`);
      } catch (e) {
        this.currentTask = 'idle';
        this.monitoringBSSID = null;
        this.$message?.error("启动监听失败");
      }
    },

    // === 🚀 新增功能：深度扫描 ===
    async toggleDeepScan() {
      if (this.currentTask === 'deep_scan') {
        await this.stopMonitor();
        return;
      }

      if(!confirm("深度扫描将清空历史捕获记录，是否继续？")) return;

      if (this.currentTask !== 'idle') await this.stopMonitor();
      
      this.currentTask = 'deep_scan';
      this.monitoringBSSID = null;
      this.deepScanClients = []; // 清空前端显示

      try {
        await axios.post('/api/v1/wifi/monitor/deep');
        this.$message?.success("深度全网扫描已启动");
      } catch (e) {
        this.currentTask = 'idle';
      }
    },

    async stopMonitor() {
      await axios.post('/api/v1/wifi/monitor/stop');
      this.currentTask = 'idle';
      this.monitoringBSSID = null;
      this.$message?.info("任务已停止");
    },

    // === 核心轮询逻辑 ===
    async pollMonitorData() {
      // 场景1：正在定向监听 -> 更新对应行的人数
      if (this.currentTask === 'monitor_target' && this.monitoringBSSID) {
        try {
          const res = await axios.get(`/api/v1/wifi/monitor/clients/${this.monitoringBSSID}`);
          const count = res.data ? res.data.length : 0;
          
          // 更新列表数据
          const target = this.networks.find(n => n.bssid === this.monitoringBSSID);
          if (target) {
            target.clientCount = count;
          }
        } catch (e) {}
      }

      // 场景2：正在深度扫描 -> 更新底部面板
      if (this.currentTask === 'deep_scan') {
        try {
          const res = await axios.get('/api/v1/wifi/monitor/deep_results');
          if (res.data) this.deepScanClients = res.data;
        } catch(e) {}
      }
    },
    
    // === 攻击跳转 ===
    async attackTarget(net) {
      // 跳转到攻击详情页，而不是直接发请求
      this.$router.push({ name: 'AttackDetail', params: { bssid: net.bssid } });
    },
    
    // === 样式辅助函数 ===
    sortBy(key) { if (this.sortKey === key) this.sortOrder *= -1; else { this.sortKey = key; this.sortOrder = 1; } },
    getEncClass(enc) { if (!enc) return 'border-gray-600 text-gray-400'; if (enc.includes('OPEN')) return 'border-red-500 text-red-400 bg-red-900/20'; return 'border-blue-600 text-blue-400 bg-blue-900/10'; },
    getLoadClass(val) { return val > 80 ? 'text-red-500 font-bold' : val > 50 ? 'text-yellow-500' : 'text-green-500'; },
    getSignalPercent(signal) { let dbm = parseInt(signal) || -100; return Math.min(100, Math.max(0, (dbm + 100) * 2)); },
    getSignalColor(signal) { let p = this.getSignalPercent(signal); return p > 70 ? 'bg-green-500' : p > 40 ? 'bg-yellow-500' : 'bg-red-500'; },
    getIntelligence(net) {
      let tags = []; const enc = (net.encryption || "").toUpperCase(); const vendor = (net.vendor || "").toLowerCase();
      if (enc.includes("OPEN")) tags.push(`<span class="text-red-400 text-xs border border-red-500 px-1 rounded bg-red-900/30">⚠️ 不安全</span>`);
      if (vendor.includes("apple")) tags.push(`<span class="text-gray-300 text-xs">🍎 Apple</span>`);
      if (parseInt(net.signal) > -50) tags.push(`<span class="text-green-400 text-xs">📍 极近</span>`);
      return tags.length > 0 ? tags.join(" ") : `<span class="text-gray-600 text-xs">-</span>`;
    }
  }
};
</script>

<style scoped>
/* 滚动条美化 */
.scrollbar-thin::-webkit-scrollbar { width: 6px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 3px; }
.scrollbar-thin::-webkit-scrollbar-thumb:hover { background: #6b7280; }

/* 深度扫描面板动画 */
.slide-fade-enter-active { transition: all 0.3s ease-out; }
.slide-fade-leave-active { transition: all 0.3s cubic-bezier(1, 0.5, 0.8, 1); }
.slide-fade-enter-from, .slide-fade-leave-to { transform: translateY(20px); opacity: 0; }
</style>