/**
 * React 渲染进程入口
 *
 * 将根组件 App 挂载到 DOM 的 #root 节点上，使用 React.StrictMode
 * 启用严格模式以便在开发阶段检测潜在问题。
 * 同时加载全局样式 index.css。
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
