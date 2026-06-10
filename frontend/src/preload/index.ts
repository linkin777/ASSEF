/**
 * Electron 预加载脚本 - 安全桥接层
 *
 * 在渲染进程与主进程之间建立安全的 IPC 通信桥梁。
 * 通过 contextBridge.exposeInMainWorld 向渲染进程暴露有限的 API：
 * - platform: 当前操作系统平台标识
 * - logToFile: 将渲染进程的日志通过 IPC 转发到主进程写入文件
 *
 * 安全设计原则：
 * - 使用 contextIsolation 隔离渲染进程与 Node.js 环境
 * - 禁用 nodeIntegration，防止渲染进程直接访问系统 API
 * - 仅通过 ipcRenderer.invoke 暴露白名单方法，不暴露 ipcRenderer.send/on
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  logToFile: (module: string, level: string, message: string, data?: unknown) =>
    ipcRenderer.invoke('log-to-file', module, level, message, data)
})
