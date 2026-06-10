type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'

/**
 * 渲染进程日志记录器接口
 *
 * 提供 debug/info/warn/error 四个级别的日志方法，
 * 每条日志同时输出到浏览器控制台和通过 IPC 写入主进程日志文件。
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

/**
 * 创建渲染进程日志记录器
 *
 * 生成的日志器会将消息以彩色格式输出到浏览器控制台，
 * 同时通过 electronAPI.logToFile 将日志转发到主进程写入磁盘文件。
 *
 * @param module - 日志模块名称，用于标识日志来源
 * @returns Logger 日志记录器实例
 */
export function createLogger(module: string): Logger {
  function write(level: LogLevel, message: string, data?: unknown): void {
    const line = formatEntry(level, module, message, data)
    const color = COLORS[level]
    console.log(`${color}${line}${COLOR_RESET}`)
    window.electronAPI.logToFile(module, level, message, data)
  }

  return {
    debug: (message, data?) => write('DEBUG', message, data),
    info: (message, data?) => write('INFO', message, data),
    warn: (message, data?) => write('WARN', message, data),
    error: (message, data?) => write('ERROR', message, data),
  }
}
