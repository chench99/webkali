import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

// 1. 引入 Element Plus 及其样式
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

// 2. 引入 Tailwind 样式
import './style.css'

// 3. 引入图标库 (如果你想全局注册，虽然 App.vue 里局部引入了，但全局注册更保险)
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

const app = createApp(App)

// 4. 注册所有图标 (可选，防止某些组件报错)
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(router)
app.use(ElementPlus) // 确保这行在 mount 之前
app.mount('#app')