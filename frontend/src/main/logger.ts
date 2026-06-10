import { appendFileSync, mkdirSync } from 'fs'
import { resolve } from 'path'

type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'

/**
 * 主进程日志记录器接口
 *
 * 提供 debug/info/warn/error 四个级别的日志方法，
 * 每条日志同时输出到终端控制台和写入对应的日志文件。
 */
export interface Logger {
  debug(message: string, data?: unknown): void
  info(message: string, data?: unknown): void
  warn(message: string, data?: unknown): void
  error(message: string, data?: unknown): void
}

const COLOR_RESET = '\x1b[0m'
const COLORS: Record<LogLevel, string> = {
  DEBUG: '\x1b[90m',
  INFO: '\x1b[36m',
  WARN: '\x1b[33m',
  ERROR: '\x1b[31m',
}

function formatTimestamp(): string {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  const h = String(now.getHours()).padStart(2, '0')
  const min = String(now.getMinutes()).padStart(2, '0')
  const s = String(now.getSeconds()).padStart(2, '0')
  const ms = String(now.getMilliseconds()).padStart(3, '0')
  return `${y}-${m}-${d} ${h}:${min}:${s}.${ms}`
}

function formatEntry(level: LogLevel, module: string, message: string, data?: unknown): string {
  const ts = formatTimestamp()
  const dataStr = data !== undefined ? ` ${JSON.stringify(data)}` : ''
  return `[${ts}] [${level}] [${module}] ${message}${dataStr}`
}

function getLogsDir(subDir: string): string {
  try {
    const electron = require('electron')
    if (electron.app && electron.app.getPath && electron.app.isPackaged) {
      return resolve(electron.app.getPath('userData'), 'logs', subDir)
    }
  } catch {
    /* use __dirname fallback */
  }
  return resolve(__dirname, '..', '..', 'logs', subDir)
}

/**
 * 创建主进程日志记录器
 *
 * 生成的日志器会将消息以彩色格式输出到终端控制台，
 * 同时将日志内容追加写入磁盘文件。日志目录位于：
 * - 打包模式：Electron userData/logs/{subDir}/{module}.log
 * - 开发模式：项目根目录/logs/{subDir}/{module}.log
 *
 * @param module - 日志模块名称，用于标识日志来源
 * @param subDir - 日志子目录名，默认为 'main'，渲染进程日志使用 'renderer'
 * @returns Logger 日志记录器实例
 */
export function createLogger(module: string, subDir = 'main'): Logger {
  const logsDir = getLogsDir(subDir)
  const logFile = resolve(logsDir, `${module}.log`)
  mkdirSync(logsDir, { recursive: true })

  function write(level: LogLevel, message: string, data?: unknown): void {
    const line = formatEntry(level, module, message, data)
    const color = COLORS[level]
    console.log(`${color}${line}${COLOR_RESET}`)
    appendFileSync(logFile, line + '\n', 'utf-8')
  }

  return {
    debug: (message, data?) => write('DEBUG', message, data),
    info: (message, data?) => write('INFO', message, data),
    warn: (message, data?) => write('WARN', message, data),
    error: (message, data?) => write('ERROR', message, data),
  }
}
