import { app, BrowserWindow, shell, ipcMain } from 'electron'
import { join } from 'path'
import { spawn } from 'child_process'
import type { ChildProcess } from 'child_process'
import http from 'http'
import { createLogger } from './logger'

const backendLogger = createLogger('backend')
const appLogger = createLogger('app')

ipcMain.handle('log-to-file', (_event, module: string, level: string, message: string, data?: unknown) => {
  const rendererLogger = createLogger(module, 'renderer')
  const method = level.toLowerCase() as 'debug' | 'info' | 'warn' | 'error'
  rendererLogger[method](message, data)
})

let pythonProcess: ChildProcess | null = null

const BACKEND_URL = 'http://localhost:8710/api/health'
const HEALTH_CHECK_TIMEOUT = 30000
const HEALTH_CHECK_INTERVAL = 500

/**
 * 等待 Python 后端服务就绪
 *
 * 通过轮询 /api/health 端点检测后端是否启动完成。
 * 每 HEALTH_CHECK_INTERVAL 毫秒检查一次，超时则抛出异常。
 * @returns 后端就绪后 resolve 的 Promise
 * @throws 超时（30秒）后 reject
 */
function waitForBackend(): Promise<void> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now()
    const poll = (): void => {
      if (Date.now() - startTime > HEALTH_CHECK_TIMEOUT) {
        reject(new Error('后端健康检查超时（30秒）'))
        return
      }
      http.get(BACKEND_URL, (res) => {
        if (res.statusCode === 200) {
          res.resume()
          resolve()
        } else {
          res.resume()
          setTimeout(poll, HEALTH_CHECK_INTERVAL)
        }
      }).on('error', () => {
        setTimeout(poll, HEALTH_CHECK_INTERVAL)
      })
    }
    poll()
  })
}

/**
 * 启动 Python 后端子进程
 *
 * 在打包模式下自动启动 Python 后端服务，并监听其标准输出、
 * 标准错误、异常和退出事件。
 * @returns 已启动的子进程对象
 */
function startPythonBackend(): ChildProcess {
  const pythonPath = join('D:\\', 'develop_tools', 'Anaconda3', 'envs', 'ASSEF', 'python.exe')
  const args = ['-m', 'backend.assef.api']
  const cwd = join('d:\\', 'JKL', 'repos', 'ASSEF')

  backendLogger.info('启动 Python 后端', { pythonPath, args: args.join(' ') })
  backendLogger.info('工作目录', { cwd })

  const proc = spawn(pythonPath, args, { cwd })

  proc.stdout?.on('data', (data: Buffer) => {
    backendLogger.info(data.toString().trimEnd())
  })

  proc.stderr?.on('data', (data: Buffer) => {
    backendLogger.error(data.toString().trimEnd())
  })

  proc.on('error', (err: Error) => {
    backendLogger.error('无法启动 Python 后端', { error: err.message })
    pythonProcess = null
  })

  proc.on('exit', (code: number | null, signal: string | null) => {
    backendLogger.info('Python 后端已退出', { code, signal })
    pythonProcess = null
  })

  return proc
}

/**
 * 优雅停止 Python 后端子进程
 *
 * 在应用退出前调用，确保后端进程被正确终止。
 */
function stopPythonBackend(): void {
  if (pythonProcess) {
    backendLogger.info('正在关闭 Python 后端...')
    pythonProcess.kill()
    pythonProcess = null
  }
}

/**
 * 创建 Electron 主窗口
 *
 * 配置窗口尺寸、自定义标题栏样式、深色背景，
 * 设置 preload 脚本并启用 contextIsolation 以保障安全性。
 * 开发模式下连接 Vite 开发服务器，生产模式下加载本地文件。
 */
function createWindow(): void {
  const mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#0a0e17',
      symbolColor: '#e0e8f0'
    },
    backgroundColor: '#0a0e17',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

/**
 * Electron 应用启动入口
 *
 * 启动流程：
 * 1. 开发模式下提示用户手动启动后端
 * 2. 生产模式下自动启动 Python 后端并等待健康检查通过
 * 3. 创建主窗口并加载前端页面
 * 4. 注册 macOS activate 事件（Dock 点击重新创建窗口）
 */
app.whenReady().then(async () => {
  if (!app.isPackaged) {
    appLogger.info('--- 开发模式 ---')
    appLogger.info('后端需手动启动: python -m backend.assef.api')
  } else {
    try {
      pythonProcess = startPythonBackend()
      appLogger.info('等待后端就绪...')
      await waitForBackend()
      appLogger.info('后端已就绪')
    } catch (err) {
      appLogger.error('后端启动失败', { error: (err as Error).message })
    }
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  if (!app.isPackaged) {
    return
  }
  stopPythonBackend()
})
