<template>
  <div class="wifi-container p-6 bg-gray-900 text-white min-h-screen font-mono">
    
    <div class="panel-header flex justify-between items-end mb-6 border-b border-gray-700 pb-4">
      <div>
        <h2 class="text-2xl font-bold flex items-center gap-3 text-blue-400">
          <span class="text-3xl">📡</span> 无线渗透控制台 <span class="text-sm text-gray-500 font-normal border border-gray-600 px-2 rounded">PRO</span>
        </h2>
        <div class="text-gray-500 text-xs mt-1">Kali Linux C2 Platform v2.2 | 深度扫描与攻击模块</div>
      </div>

      <div class="system-status flex gap-4 text-xs bg-gray-800 px-4 py-2 rounded border border-gray-700 shadow-inner">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
          <span class="text-gray-400">核心:</span>
          <span class="text-green-400">运行中</span>
        </div>
        <div class="flex items-center gap-2 border-l border-gray-600 pl-4">
          <span class="text-gray-400">在线人数:</span>
          <span class="text-white font-bold">{{ systemStatus.online_users || 1 }}</span>
        </div>
        <div class="flex items-center gap-2 border-l border-gray-600 pl-4">
          <span class="text-gray-400">CPU负载:</span>
          <span :class="getLoadClass(systemStatus.cpu_percent)">{{ systemStatus.cpu_percent || 0 }}%</span>
        </div>
      </div>
    </div>

    <div class="toolbar flex flex-wrap gap-4 justify-between items-center mb-4 bg-gray-800 p-3 rounded border border-gray-700">
      
      <div class="flex gap-3 items-center">
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-400">选择网卡:</span>
          <select 
            v-model="selectedInterface" 
            class="bg-gray-900 border border-gray-600 text-white px-3 py-1.5 rounded text-sm focus:border-blue-500 outline-none"
          >
            <option value="" disabled>请选择监听接口...</option>
            <option v-for="iface in interfaces" :key="iface.name" :value="iface.name">
              {{ iface.name }} {{ iface.is_wireless ? '(无线)' : '' }}
            </option>
          </select>
          <button @click="fetchInterfaces" title="刷新网卡列表" class="text-gray-400 hover:text-white px-2">↻</button>
        </div>

        <div class="search-box relative ml-4">
          <span class="absolute left-2 top-1.5 text-gray-500 text-xs">🔍</span>
          <input 
            v-model="searchQuery"
            type="text" 
            placeholder="搜索 SSID / MAC / 厂商..." 
            class="bg-gray-900 border border-gray-600 text-white pl-8 pr-4 py-1.5 rounded focus:outline-none focus:border-blue-500 w-64 text-sm"
          >
        </div>
      </div>

      <div class="controls flex gap-3 items-center">
        <div class="text-xs text-gray-500 mr-2">
          发现目标: {{ filteredNetworks.length }}
        </div>
        <button 
          class="px-5 py-2 rounded bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 disabled:opacity-50 transition-all shadow-lg flex items-center gap-2 font-bold text-sm"
          :disabled="isScanning"
          @click="startScan"
        >
          <span v-if="isScanning" class="animate-spin">⏳</span>
          {{ isScanning ? '深度扫描中...' : '开始扫描 (SCAN)' }}
        </button>
      </div>
    </div>

    <div class="network-list bg-gray-800 rounded-lg shadow-xl overflow-hidden border border-gray-700">
      <table class="w-full text-left text-sm">
        <thead class="bg-gray-900 text-gray-400 uppercase tracking-wider">
          <tr>
            <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('ssid')">ESSID ⇅</th>
            <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('bssid')">BSSID (MAC) ⇅</th>
            <th class="p-4 border-b border-gray-700">设备厂商</th> <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('channel')">信道/频段 ⇅</th>
            <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('encryption')">加密方式 ⇅</th>
            <th class="p-4 border-b border-gray-700 cursor-pointer hover:text-white" @click="sortBy('signal')">信号强度 ⇅</th>
            <th class="p-4 border-b border-gray-700">情报分析</th> <th class="p-4 text-right border-b border-gray-700">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-700">
          <tr v-if="filteredNetworks.length === 0 && !isScanning">
            <td colspan="8" class="p-12 text-center text-gray-500">
              <div class="text-4xl mb-2">🔭</div>
              <div>暂无数据，请选择网卡并点击扫描</div>
            </td>
          </tr>

          <tr v-for="(net, index) in filteredNetworks" :key="index" class="hover:bg-gray-700 transition-colors group">
            <td class="p-4 font-bold text-white group-hover:text-blue-300 transition-colors">
              {{ net.ssid || '<隐藏网络>' }}
            </td>
            
            <td class="p-4 text-gray-400 font-mono text-xs">
              {{ net.bssid }}
            </td>
            
            <td class="p-4 text-gray-300 text-xs">
              {{ net.vendor || '未知厂商' }}
            </td>
            
            <td class="p-4">
              <div class="flex flex-col">
                <span class="text-white font-bold text-xs">CH {{ net.channel }}</span>
                <span class="text-xs text-gray-500 scale-90 origin-left">{{ net.band || '2.4GHz' }}</span>
              </div>
            </td>
            
            <td class="p-4">
              <span class="px-2 py-0.5 rounded text-xs font-bold border" :class="getEncClass(net.encryption)">
                {{ net.encryption }}
              </span>
            </td>
            
            <td class="p-4">
              <div class="w-24 bg-gray-900 rounded-full h-1.5 mt-1 overflow-hidden">
                <div class="h-full transition-all duration-500" :class="getSignalColor(net.signal)" :style="{ width: getSignalPercent(net.signal) + '%' }"></div>
              </div>
              <div class="text-xs text-gray-500 mt-1 flex justify-between w-24">
                <span>{{ net.signal }} dBm</span>
                <span>{{ getSignalPercent(net.signal) }}%</span>
              </div>
            </td>
            
            <td class="p-4">
              <span v-html="getIntelligence(net)"></span>
            </td>
            
            <td class="p-4 text-right">
              <button 
                class="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded text-xs transition-colors shadow hover:shadow-red-500/50 flex items-center gap-1 ml-auto" 
                @click="attackTarget(net)"
              >
                <span>☠️</span> 攻击
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
      searchQuery: "",
      selectedInterface: "", // 用户选中的网卡
      interfaces: [],        // 网卡列表
      sortKey: 'signal',
      sortOrder: -1,
      networks: [],
      systemStatus: { online_users: 1, cpu_percent: 0 },
      statusTimer: null
    };
  },
  computed: {
    // 过滤 + 排序逻辑
    filteredNetworks() {
      let result = this.networks;
      // 1. 过滤
      if (this.searchQuery) {
        const q = this.searchQuery.toLowerCase();
        result = result.filter(n => 
          (n.ssid && n.ssid.toLowerCase().includes(q)) || 
          (n.bssid && n.bssid.toLowerCase().includes(q)) || 
          (n.vendor && n.vendor.toLowerCase().includes(q))
        );
      }
      // 2. 排序
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
    this.fetchInterfaces(); // 页面加载时自动获取网卡
    this.statusTimer = setInterval(this.fetchSystemStatus, 5000);
  },
  beforeDestroy() {
    if (this.statusTimer) clearInterval(this.statusTimer);
  },
  methods: {
    // 获取系统状态
    async fetchSystemStatus() {
      try { const res = await axios.get('/api/v1/system/status'); if (res.data) this.systemStatus = res.data; } catch (e) {}
    },
    
    // 获取网卡列表
    async fetchInterfaces() {
      try {
        const res = await axios.get('/api/v1/wifi/interfaces');
        if (res.data && res.data.interfaces) {
          this.interfaces = res.data.interfaces;
          // 默认选中第一个无线网卡
          const wireless = this.interfaces.find(i => i.is_wireless);
          if (wireless) this.selectedInterface = wireless.name;
          else if (this.interfaces.length > 0) this.selectedInterface = this.interfaces[0].name;
        }
      } catch (error) {
        console.error("获取网卡失败", error);
      }
    },

    // 开始扫描
    async startScan() {
      this.isScanning = true;
      try {
        // 传递 interface 参数给后端
        const payload = this.selectedInterface ? { interface: this.selectedInterface } : {};
        const res = await axios.post('/api/v1/wifi/scan/start', payload);
        
        if (res.data.networks) this.networks = res.data.networks;
        else if (Array.isArray(res.data)) this.networks = res.data;
        
        if (this.networks.length > 0) this.$message?.success(`扫描完成: 更新 ${this.networks.length} 个目标`);
        else this.$message?.warning("未发现目标");
      } catch (error) {
        console.error("Scan Error:", error);
        alert("扫描失败: " + (error.response?.data?.detail || error.message));
      } finally {
        this.isScanning = false;
      }
    },
    
    // 攻击目标
    async attackTarget(net) {
      if(!confirm(`⚠️ 警告: 确认对 ${net.ssid} 执行 Deauth (断网) 攻击?`)) return;
      try {
        await axios.post('/api/v1/wifi/capture/start', { bssid: net.bssid, channel: net.channel });
        alert("🚀 攻击指令已发送至后台！");
      } catch(e) { alert("❌ 攻击失败: " + e.message); }
    },
    
    // 排序切换
    sortBy(key) { if (this.sortKey === key) this.sortOrder *= -1; else { this.sortKey = key; this.sortOrder = 1; } },
    
    // 样式与辅助函数
    getEncClass(enc) {
      if (!enc) return 'border-gray-600 text-gray-400';
      if (enc.includes('OPEN')) return 'border-red-500 text-red-400 bg-red-900/20';
      if (enc.includes('WEP')) return 'border-orange-500 text-orange-400 bg-orange-900/20';
      return 'border-blue-600 text-blue-400 bg-blue-900/10';
    },
    getLoadClass(val) { return val > 80 ? 'text-red-500 font-bold' : val > 50 ? 'text-yellow-500' : 'text-green-500'; },
    getSignalPercent(signal) { let dbm = parseInt(signal) || -100; if (dbm > -50) return 100; if (dbm < -100) return 0; return Math.min(100, Math.max(0, (dbm + 100) * 2)); },
    getSignalColor(signal) { let p = this.getSignalPercent(signal); return p > 70 ? 'bg-green-500' : p > 40 ? 'bg-yellow-500' : 'bg-red-500'; },
    
    // 情报分析生成 HTML
    getIntelligence(net) {
      let tags = []; const enc = (net.encryption || "").toUpperCase(); const vendor = (net.vendor || "").toLowerCase();
      
      // 风险标签
      if (enc.includes("OPEN")) tags.push(`<span class="text-red-400 text-xs border border-red-500 px-1 rounded bg-red-900/30">⚠️ 不安全</span>`);
      if (enc.includes("WEP")) tags.push(`<span class="text-orange-400 text-xs border border-orange-500 px-1 rounded">🔓 弱加密</span>`);
      
      // 设备标签
      if (vendor.includes("apple")) tags.push(`<span class="text-gray-300 text-xs">🍎 Apple</span>`);
      if (vendor.includes("xiaomi")) tags.push(`<span class="text-orange-300 text-xs">📱 小米</span>`);
      if (vendor.includes("tp-link")) tags.push(`<span class="text-blue-300 text-xs">🌐 路由</span>`);

      // 距离标签
      if (parseInt(net.signal) > -50) tags.push(`<span class="text-green-400 text-xs">📍 极近</span>`);
      
      return tags.length > 0 ? tags.join(" ") : `<span class="text-gray-600 text-xs">-</span>`;
    }
  }
};
</script>

<style scoped>
.animate-spin { animation: spin 1s linear infinite; } @keyframes spin { 100% { transform: rotate(360deg); } }
.animate-pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; } @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
</style>