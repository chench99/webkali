<template>
  <div class="ai-terminal-container">
    <div class="terminal-header">
      <div class="header-title">
        <i class="el-icon-cpu"></i> 战术参谋部 (AI Advisor)
      </div>
      <div class="mode-selector">
        <div 
          class="mode-btn" 
          :class="{ active: currentMode === 'general' }"
          @click="switchMode('general')"
        >
          <span class="icon">💬</span> 普通模式
        </div>
        <div 
          class="mode-btn" 
          :class="{ active: currentMode === 'attack' }"
          @click="switchMode('attack')"
        >
          <span class="icon">⚔️</span> 红队渗透
        </div>
        <div 
          class="mode-btn" 
          :class="{ active: currentMode === 'code' }"
          @click="switchMode('code')"
        >
          <span class="icon">💻</span> 代码审计
        </div>
      </div>
    </div>

    <div class="chat-window" ref="chatContainer">
      <div class="message ai-message">
        <div class="avatar">🤖</div>
        <div class="content">
          <div class="sender">SYSTEM</div>
          <div class="text">
            终端已就绪。<br>
            当前模式: <span class="highlight">{{ modeName }}</span><br>
            {{ modeDescription }}
          </div>
        </div>
      </div>

      <div 
        v-for="(msg, index) in chatHistory" 
        :key="index" 
        class="message" 
        :class="msg.role === 'user' ? 'user-message' : 'ai-message'"
      >
        <div class="avatar">{{ msg.role === 'user' ? '👨‍💻' : '🤖' }}</div>
        
        <div class="content">
          <div class="sender">{{ msg.role === 'user' ? 'OPERATOR' : 'ADVISOR' }}</div>
          
          <div v-if="msg.role === 'user'" class="text">{{ msg.content }}</div>
          
          <div 
            v-else 
            class="text ai-text-content" 
            v-html="parseThinkContent(msg.content)"
          ></div>
        </div>
      </div>

      <div v-if="isLoading" class="message ai-message">
        <div class="avatar">⏳</div>
        <div class="content">
          <div class="text blinking">
            {{ currentMode === 'general' ? '正在输入...' : '正在进行战术推演 (Thinking)...' }}
          </div>
        </div>
      </div>
    </div>

    <div class="input-area">
      <textarea 
        v-model="inputPrompt" 
        @keydown.enter.prevent="sendMessage"
        placeholder="输入指令..."
        :disabled="isLoading"
      ></textarea>
      <button @click="sendMessage" :disabled="isLoading || !inputPrompt.trim()">
        SEND
      </button>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: "AiAdvisor",
  data() {
    return {
      currentMode: "general", // general, attack, code
      inputPrompt: "",
      isLoading: false,
      chatHistory: []
    };
  },
  computed: {
    modeName() {
      const map = {
        'general': '通用咨询 (General)',
        'attack': '红队战术 (Red Team)',
        'code': '代码开发 (DevSecOps)'
      };
      return map[this.currentMode];
    },
    modeDescription() {
      if (this.currentMode === 'general') return '适合闲聊、概念解释。';
      return '已开启深度思考模式。AI 将先进行逻辑推演，再给出方案。';
    }
  },
  methods: {
    switchMode(mode) {
      this.currentMode = mode;
      // 切换模式时清空历史或提示用户（可选）
      this.chatHistory.push({
        role: 'ai',
        content: `🔄 模式已切换为: ${this.modeName}`
      });
    },

    // 核心：解析 <think> 标签并替换为 HTML 样式
    parseThinkContent(text) {
      if (!text) return "";
      
      // 防止 XSS 的简单处理（在渲染 HTML 前）
      // 如果你的内容包含真实代码，这里可能需要更复杂的 Markdown 解析器
      // 这里为了演示核心功能，主要处理 <think> 标签
      
      let formatted = text;

      // 1. 将 <think> 替换为带样式的 div 开始
      if (formatted.includes('<think>')) {
        formatted = formatted.replace(
          '<think>', 
          `<div class="think-block"><div class="think-header">🧠 深度思维链 (Chain of Thought)</div>`
        );
      }
      
      // 2. 将 </think> 替换为 div 结束
      if (formatted.includes('</think>')) {
        formatted = formatted.replace('</think>', '</div>');
      }

      // 3. 将换行符转换为 <br>，保证在 v-html 中换行
      // 注意：这会破坏 Markdown 代码块的显示，最完美的方案是引入 'marked' 库
      // 如果你没装 marked，可以用这个简单的正则保留换行
      return formatted.replace(/\n/g, '<br>'); 
    },

    async sendMessage() {
      if (!this.inputPrompt.trim()) return;

      const prompt = this.inputPrompt;
      this.chatHistory.push({ role: 'user', content: prompt });
      this.inputPrompt = "";
      this.scrollToBottom();

      this.isLoading = true;

      try {
        const res = await axios.post('/api/v1/ai/chat', {
          prompt: prompt,
          mode: this.currentMode
        });

        // 获取结果
        let aiReply = "";
        if (res.data && res.data.result) {
          aiReply = res.data.result;
        } else {
          aiReply = "❌ 数据格式错误";
        }

        this.chatHistory.push({ role: 'ai', content: aiReply });

      } catch (error) {
        console.error(error);
        this.chatHistory.push({ role: 'ai', content: "❌ 连接失败，请检查后端日志。" });
      } finally {
        this.isLoading = false;
        this.scrollToBottom();
      }
    },
    
    scrollToBottom() {
      this.$nextTick(() => {
        const container = this.$refs.chatContainer;
        if (container) container.scrollTop = container.scrollHeight;
      });
    }
  }
};
</script>

<style scoped>
/* =========== 整体容器 =========== */
.ai-terminal-container {
  display: flex;
  flex-direction: column;
  height: 85vh;
  background-color: #0d1117;
  color: #c9d1d9;
  font-family: 'Courier New', monospace;
  border: 1px solid #30363d;
  border-radius: 8px;
  box-shadow: 0 0 15px rgba(0, 0, 0, 0.6);
  overflow: hidden;
}

/* =========== 头部 =========== */
.terminal-header {
  background-color: #161b22;
  border-bottom: 1px solid #30363d;
  padding: 10px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title {
  color: #58a6ff;
  font-weight: bold;
  font-size: 1.1em;
}

.mode-selector {
  display: flex;
  gap: 8px;
}

.mode-btn {
  background: #21262d;
  border: 1px solid #30363d;
  padding: 5px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85em;
  color: #8b949e;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 5px;
}

.mode-btn:hover {
  background: #30363d;
  color: white;
}

/* 激活状态：通用是蓝色，红队是红色，代码是绿色 */
.mode-btn.active {
  color: white;
  border-color: transparent;
}
.mode-btn.active:nth-child(1) { background-color: #1f6feb; } /* Blue */
.mode-btn.active:nth-child(2) { background-color: #da3633; } /* Red */
.mode-btn.active:nth-child(3) { background-color: #238636; } /* Green */

/* =========== 聊天窗口 =========== */
.chat-window {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background-image: radial-gradient(#21262d 1px, transparent 1px);
  background-size: 20px 20px;
}

.message {
  display: flex;
  margin-bottom: 25px;
  align-items: flex-start;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2em;
  margin-right: 12px;
  background: #21262d;
  border: 1px solid #30363d;
}

.content {
  max-width: 85%;
  flex: 1;
}

.sender {
  font-size: 0.75em;
  color: #8b949e;
  margin-bottom: 4px;
}

.text {
  background: #161b22;
  border: 1px solid #30363d;
  padding: 12px;
  border-radius: 6px;
  line-height: 1.6;
  font-size: 0.95em;
}

.user-message {
  flex-direction: row-reverse;
}
.user-message .avatar {
  margin-right: 0;
  margin-left: 12px;
  background: #1f6feb;
}
.user-message .text {
  background: #1f2428;
  border-color: #1f6feb;
  color: white;
}
.user-message .content {
  text-align: right;
}

.ai-message .avatar {
  background: #238636;
}

/* =========== 深度思考样式 (关键) =========== */
/* 这里的样式对应 parseThinkContent 生成的 HTML */
::v-deep .think-block {
  background-color: #1c1c1c;
  border-left: 3px solid #8b949e;
  padding: 10px 15px;
  margin-bottom: 15px;
  color: #999;
  font-size: 0.9em;
  border-radius: 4px;
  font-style: italic;
}

::v-deep .think-header {
  color: #d2a8ff; /* 浅紫色 */
  font-weight: bold;
  font-style: normal;
  margin-bottom: 5px;
  border-bottom: 1px dashed #444;
  padding-bottom: 5px;
  display: inline-block;
}

/* =========== 底部输入 =========== */
.input-area {
  padding: 15px;
  background: #161b22;
  border-top: 1px solid #30363d;
  display: flex;
  gap: 10px;
}

textarea {
  flex: 1;
  background: #0d1117;
  border: 1px solid #30363d;
  color: white;
  padding: 10px;
  border-radius: 4px;
  resize: none;
  height: 50px;
  font-family: inherit;
}
textarea:focus { outline: none; border-color: #58a6ff; }

button {
  width: 80px;
  background: #238636;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}
button:disabled {
  background: #30363d;
  cursor: not-allowed;
  color: #6e7681;
}

.blinking {
  animation: blink 1.5s infinite;
}
@keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
</style>