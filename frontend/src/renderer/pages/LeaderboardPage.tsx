import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import * as Tabs from '@radix-ui/react-tabs'
import { useAppStore } from '../store'
import { useArenaStore } from '../store/arenaSlice'
import { startBenchmark, cancelTask } from '../api/client'
import { TaskWebSocketManager } from '../api/websocket'
import type { BenchmarkRequest, ProgressEvent } from '../types'

type CellStatus = 'waiting' | 'running' | 'completed' | 'failed'

interface CellState {
  status: CellStatus
  passRate?: number
}

interface BenchmarkResult {
  model_name: string
  pass_rate: number
  bloat_rate: number
  avg_time: number
}

interface ModelOption {
  key: string
  label: string
  modelName: string
}

interface TargetOption {
  name: string
  description: string
}

type TabKey = 'pass_rate' | 'bloat_rate' | 'avg_time'

const TAB_CONFIG: { key: TabKey; label: string; dataKey: keyof BenchmarkResult; unit: string; barColor: string; lowerBetter: boolean }[] = [
  { key: 'pass_rate', label: '修复通过率', dataKey: 'pass_rate', unit: '%', barColor: '#22d3ee', lowerBetter: false },
  { key: 'bloat_rate', label: '代码膨胀率', dataKey: 'bloat_rate', unit: '%', barColor: '#f59e0b', lowerBetter: true },
  { key: 'avg_time', label: '平均耗时', dataKey: 'avg_time', unit: 's', barColor: '#a855f7', lowerBetter: true },
]

/**
 * 从配置中的后端模型列表转换为模型选项列表，用于 UI 展示。
 *
 * @param configModels - 配置中的模型列表，包含 backend 和 model 字段
 * @returns 格式化后的模型选项数组，包含 key、label 和 modelName
 */
function getModelOptions(configModels: { backend: string; model: string }[]): ModelOption[] {
  return configModels.map((c, i) => {
    const key = c.model || `model_${i}`
    return {
      key,
      label: `${c.model} (${c.backend})`,
      modelName: c.model,
    }
  })
}

/**
 * 从配置中的靶机列表转换为靶机选项列表，用于 UI 展示。
 *
 * @param configTargets - 配置中的靶机列表，包含 name 和 description 字段
 * @returns 格式化后的靶机选项数组
 */
function getTargetOptions(configTargets: { name: string; description: string }[]): TargetOption[] {
  return configTargets.map((t) => ({
    name: t.name,
    description: t.description,
  }))
}

interface LeaderboardPageInternalProps {
  modelOptions: ModelOption[]
  targetOptions: TargetOption[]
}

/**
 * 排行榜页面内部实现组件，处理模型/靶机选择、启动评测、进度展示和取消等核心逻辑。
 *
 * @param modelOptions - 可选的模型列表
 * @param targetOptions - 可选的靶机列表
 * @returns 排行榜页面主体 JSX
 */
function LeaderboardPageInternal({ modelOptions, targetOptions }: LeaderboardPageInternalProps): JSX.Element {
  const setActiveTask = useArenaStore((s) => s.setActiveTask)

  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [selectedTargets, setSelectedTargets] = useState<string[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [cellStates, setCellStates] = useState<Record<string, Record<string, CellState>>>({})
  const [results, setResults] = useState<BenchmarkResult[] | null>(null)
  const [completeCount, setCompleteCount] = useState(0)
  const [totalCount, setTotalCount] = useState(0)

  const wsRef = useRef<TaskWebSocketManager | null>(null)
  const taskIdRef = useRef<string | null>(null)

  /**
   * 处理 WebSocket 进度事件，更新 cell 状态和最终结果。
   *
   * @param event - 从 WebSocket 接收到的进度事件
   */
  const handleProgressEvent = useCallback((event: ProgressEvent) => {
    if (event.type === 'benchmark_progress') {
      const data = event.data
      const currentTarget = data.current_target as string | undefined
      const currentModel = data.current_model as string | undefined
      const rawStatus = data.status as string | undefined
      const passRate = typeof data.pass_rate === 'number' ? data.pass_rate : undefined
      const cc = typeof data.complete_count === 'number' ? data.complete_count : 0
      const tc = typeof data.total_count === 'number' ? data.total_count : 0

      setCompleteCount(cc)
      setTotalCount(tc)

      if (!currentTarget || !currentModel || !rawStatus) return

      const cellStatus: CellStatus =
        rawStatus === 'completed' ? 'completed'
        : rawStatus === 'failed' ? 'failed'
        : 'running'

      setCellStates((prev) => {
        const prevTarget = prev[currentTarget] ?? {}
        return {
          ...prev,
          [currentTarget]: {
            ...prevTarget,
            [currentModel]: { status: cellStatus, passRate },
          },
        }
      })
    } else if (event.type === 'task_done') {
      const data = event.data
      const rawResults = data.results
      if (Array.isArray(rawResults)) {
        setResults(rawResults as BenchmarkResult[])
      }
      setIsRunning(false)
      setActiveTask(null)
    }
  }, [setActiveTask])

  useEffect(() => {
    return () => {
      wsRef.current?.disconnect()
    }
  }, [])

  /**
   * 切换指定模型的选中状态（运行时不可操作）。
   *
   * @param key - 模型的唯一标识
   */
  const handleToggleModel = useCallback((key: string) => {
    if (isRunning) return
    setSelectedModels((prev) =>
      prev.includes(key) ? prev.filter((m) => m !== key) : [...prev, key]
    )
  }, [isRunning])

  const handleToggleTarget = useCallback((name: string) => {
    if (isRunning) return
    setSelectedTargets((prev) =>
      prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name]
    )
  }, [isRunning])

  /**
   * 启动多模型基准评测任务。初始化 cell 状态矩阵并建立 WebSocket 连接监听进度。
   */
  const handleStart = useCallback(async () => {
    if (selectedModels.length === 0 || selectedTargets.length === 0) return

    setIsRunning(true)
    setResults(null)

    const initCellStates: Record<string, Record<string, CellState>> = {}
    for (const target of selectedTargets) {
      initCellStates[target] = {}
      for (const model of selectedModels) {
        initCellStates[target][model] = { status: 'waiting' }
      }
    }
    setCellStates(initCellStates)
    setCompleteCount(0)
    setTotalCount(selectedTargets.length * selectedModels.length)

    try {
      const req: BenchmarkRequest = {
        target_names: selectedTargets,
        backend_names: selectedModels,
      }
      const res = await startBenchmark(req)
      setTaskId(res.task_id)
      taskIdRef.current = res.task_id
      setActiveTask(res.task_id)

      if (!wsRef.current) {
        wsRef.current = new TaskWebSocketManager()
      }
      wsRef.current.connect(res.task_id, handleProgressEvent)
    } catch {
      setIsRunning(false)
      setActiveTask(null)
    }
  }, [selectedModels, selectedTargets, setActiveTask, handleProgressEvent])

  /**
   * 取消当前正在运行的评测任务，断开 WebSocket 连接并重置所有状态。
   */
  const handleCancel = useCallback(async () => {
    const tid = taskIdRef.current
    if (tid) {
      try {
        await cancelTask(tid)
      } catch {
        /* ignore cancel errors */
      }
      wsRef.current?.disconnect()
    }
    setIsRunning(false)
    setTaskId(null)
    taskIdRef.current = null
    setCellStates({})
    setResults(null)
    setCompleteCount(0)
    setTotalCount(0)
    setActiveTask(null)
  }, [setActiveTask])

  const canStart = selectedModels.length > 0 && selectedTargets.length > 0 && !isRunning
  const showProgress = isRunning || (results !== null && results.length > 0)

  return (
    <div className="flex h-full flex-col">
      <h1 className="mb-6 text-3xl font-bold text-accent-cyan">模型排行榜</h1>

      <div className="mb-6 rounded-lg border border-border bg-card p-5">
        <h2 className="mb-4 text-lg font-semibold text-foreground">评测控制</h2>

        <div className="mb-5">
          <label className="mb-2 block text-sm text-muted-foreground">选择模型</label>
          <div className="flex flex-wrap gap-2">
            {modelOptions.map((m) => {
              const checked = selectedModels.includes(m.key)
              return (
                <label
                  key={m.key}
                  className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-1.5 text-sm transition-colors ${
                    isRunning ? 'cursor-not-allowed opacity-60' : ''
                  } ${
                    checked
                      ? 'border-accent-cyan bg-accent-cyan/10 text-accent-cyan/80'
                      : 'border-border bg-secondary text-foreground hover:border-ring/50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => handleToggleModel(m.key)}
                    disabled={isRunning}
                    className="sr-only"
                  />
                  <span
                    className={`flex h-3.5 w-3.5 items-center justify-center rounded border ${
                      checked ? 'border-accent-cyan bg-primary' : 'border-muted-foreground/50'
                    }`}
                  >
                    {checked && <span className="text-xs font-bold text-card">✓</span>}
                  </span>
                  {m.label}
                </label>
              )
            })}
          </div>
        </div>

        <div className="mb-5">
          <label className="mb-2 block text-sm text-muted-foreground">选择靶机</label>
          <div className="flex flex-wrap gap-2">
            {targetOptions.map((t) => {
              const checked = selectedTargets.includes(t.name)
              return (
                <label
                  key={t.name}
                  title={t.description}
                  className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-1.5 text-sm transition-colors ${
                    isRunning ? 'cursor-not-allowed opacity-60' : ''
                  } ${
                    checked
                      ? 'border-accent-cyan bg-accent-cyan/10 text-accent-cyan/80'
                      : 'border-border bg-secondary text-foreground hover:border-ring/50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => handleToggleTarget(t.name)}
                    disabled={isRunning}
                    className="sr-only"
                  />
                  <span
                    className={`flex h-3.5 w-3.5 items-center justify-center rounded border ${
                      checked ? 'border-accent-cyan bg-primary' : 'border-muted-foreground/50'
                    }`}
                  >
                    {checked && <span className="text-xs font-bold text-card">✓</span>}
                  </span>
                  {t.name}
                </label>
              )
            })}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleStart}
            disabled={!canStart}
            className="rounded bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            🚀 启动评测
          </button>
          {isRunning && (
            <button
              onClick={handleCancel}
              className="rounded border border-destructive/50 bg-destructive/10 px-5 py-2 text-sm font-semibold text-destructive transition-colors hover:bg-destructive/20"
            >
              ⏹ 取消
            </button>
          )}
          {isRunning && (
            <span className="ml-2 text-sm text-muted-foreground">
              进度: {completeCount}/{totalCount}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <AnimatePresence mode="wait">
          {results !== null ? (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.4 }}
            >
              <ResultsPanel results={results} />
            </motion.div>
          ) : showProgress ? (
            <motion.div
              key="progress"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              <ProgressTable
                selectedTargets={selectedTargets}
                selectedModels={selectedModels}
                cellStates={cellStates}
                getModelLabel={(key) => {
                  const opt = modelOptions.find((m) => m.key === key)
                  return opt?.modelName ?? key
                }}
              />
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex h-48 items-center justify-center text-muted-foreground"
            >
              选择模型和靶机后启动评测
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

interface ProgressTableProps {
  selectedTargets: string[]
  selectedModels: string[]
  cellStates: Record<string, Record<string, CellState>>
  getModelLabel: (key: string) => string
}

/**
 * 评测进度表格组件，以靶机为行、模型为列展示每个单元的评测状态。
 *
 * @param selectedTargets - 选中的靶机列表
 * @param selectedModels - 选中的模型列表
 * @param cellStates - 靶机×模型的状态映射
 * @param getModelLabel - 根据模型 key 获取显示标签的函数
 * @returns 进度表格 JSX
 */
function ProgressTable({
  selectedTargets,
  selectedModels,
  cellStates,
  getModelLabel,
}: ProgressTableProps): JSX.Element {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-card">
            <th className="border-b border-border px-4 py-3 text-left text-sm font-semibold text-foreground">
              靶机 \ 模型
            </th>
            {selectedModels.map((model) => (
              <th
                key={model}
                className="border-b border-border px-4 py-3 text-center text-sm font-semibold text-foreground"
              >
                {getModelLabel(model)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {selectedTargets.map((target) => (
            <tr key={target} className="border-b border-border/50 last:border-b-0">
              <td className="px-4 py-3 text-sm font-medium text-foreground">{target}</td>
              {selectedModels.map((model) => {
                const state = cellStates[target]?.[model] ?? { status: 'waiting' as const }
                return (
                  <td
                    key={model}
                    className="relative px-3 py-3 text-center"
                  >
                    <CellContent state={state} />
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface CellContentProps {
  state: CellState
}

/**
 * 进度单元格内容组件，根据状态显示等待/运行中/完成/失败的不同 UI。
 *
 * @param state - 单元格的状态信息
 * @returns 单元格内容 JSX
 */
function CellContent({ state }: CellContentProps): JSX.Element {
  return (
    <div className="relative flex items-center justify-center">
      {state.status === 'running' && (
        <motion.div
          className="absolute inset-0 rounded-md bg-accent-cyan/10"
          animate={{ opacity: [0.1, 0.4, 0.1] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}
      <AnimatePresence mode="wait">
        <motion.div
          key={state.status}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.8 }}
          transition={{ duration: 0.2 }}
          className="relative z-10 text-sm"
        >
          {state.status === 'waiting' && <span className="text-muted-foreground/70">⏳ 等待</span>}
          {state.status === 'running' && (
            <motion.span
              className="text-accent-cyan"
              animate={{ opacity: [0.6, 1, 0.6] }}
              transition={{ duration: 1, repeat: Infinity }}
            >
              🔄 运行中
            </motion.span>
          )}
          {state.status === 'completed' && (
            <span className="font-semibold text-emerald-400">
              ✅ {state.passRate != null ? `${state.passRate.toFixed(1)}%` : '完成'}
            </span>
          )}
          {state.status === 'failed' && <span className="font-semibold text-red-400">❌ 失败</span>}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

interface ResultsPanelProps {
  results: BenchmarkResult[]
}

/**
 * 评测结果展示面板，使用 Tab 切换查看通过率、代码膨胀率、平均耗时等维度的图表。
 *
 * @param results - 评测结果数组
 * @returns 结果面板 JSX
 */
function ResultsPanel({ results }: ResultsPanelProps): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>('pass_rate')

  return (
    <Tabs.Root
      value={activeTab}
      onValueChange={(v) => setActiveTab(v as TabKey)}
      className="flex flex-col"
    >
      <Tabs.List className="mb-4 flex gap-1 rounded-lg bg-card p-1">
        {TAB_CONFIG.map((tab) => (
          <Tabs.Trigger
            key={tab.key}
            value={tab.key}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab.label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>

      {TAB_CONFIG.map((tab) => (
        <Tabs.Content key={tab.key} value={tab.key} className="flex-1">
          <ResultChart
            results={results}
            dataKey={tab.dataKey}
            unit={tab.unit}
            barColor={tab.barColor}
            lowerBetter={tab.lowerBetter}
            label={tab.label}
          />
        </Tabs.Content>
      ))}
    </Tabs.Root>
  )
}

interface ChartDataItem {
  name: string
  value: number
}

interface ResultChartProps {
  results: BenchmarkResult[]
  dataKey: keyof BenchmarkResult
  unit: string
  barColor: string
  lowerBetter: boolean
  label: string
}

/**
 * 单维度柱状图组件，使用 Recharts 绘制水平柱状图并附带排名表。
 *
 * @param results - 评测结果数据
 * @param dataKey - 要展示的指标字段名
 * @param unit - 指标单位
 * @param barColor - 柱状图颜色
 * @param lowerBetter - 是否为越小越好的指标
 * @param label - 图表标题
 * @returns 柱状图 JSX
 */
function ResultChart({
  results,
  dataKey,
  unit,
  barColor,
  lowerBetter,
  label,
}: ResultChartProps): JSX.Element {
  const chartData: ChartDataItem[] = useMemo(() => {
    const sorted = [...results].sort((a, b) => {
      const aVal = a[dataKey] as number
      const bVal = b[dataKey] as number
      return lowerBetter ? aVal - bVal : bVal - aVal
    })
    return sorted.map((r) => ({
      name: r.model_name,
      value: r[dataKey] as number,
    }))
  }, [results, dataKey, lowerBetter])

  const barSize = 32
  const chartHeight = Math.max(chartData.length * (barSize + 12) + 40, 200)

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-foreground">{label}</h3>
        <span className="text-xs text-muted-foreground">
          {lowerBetter ? '↓ 越低越好' : '↑ 越高越好'}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
        >
          <XAxis
            type="number"
            tick={{ fill: '#9ca3af', fontSize: 12 }}
            axisLine={{ stroke: '#374151' }}
            tickLine={false}
            unit={unit}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fill: '#9ca3af', fontSize: 12 }}
            axisLine={{ stroke: '#374151' }}
            tickLine={false}
            width={120}
          />
          <Tooltip content={<ChartTooltip unit={unit} />} />
          <Bar
            dataKey="value"
            fill={barColor}
            radius={[0, 4, 4, 0]}
            barSize={barSize}
            animationDuration={800}
            animationEasing="ease-out"
          />
        </BarChart>
      </ResponsiveContainer>
      <RankingTable chartData={chartData} unit={unit} />
    </div>
  )
}

interface ChartTooltipProps {
  unit: string
  payload?: { value: number }[]
  label?: string
  active?: boolean
}

/**
 * 图表自定义提示框组件。
 *
 * @param active - 是否处于 hover 状态
 * @param payload - 当前数据点的值数组
 * @param label - 数据点的标签（模型名称）
 * @param unit - 指标单位
 * @returns 提示框 JSX，非活跃时返回 null
 */
function ChartTooltip({ active, payload, label, unit }: ChartTooltipProps): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null

  return (
    <div className="rounded border border-border bg-secondary px-3 py-2 shadow-lg">
      <p className="text-sm font-medium text-foreground">{label}</p>
      <p className="text-sm text-accent-cyan">
        {payload[0].value.toFixed(2)}{unit}
      </p>
    </div>
  )
}

interface RankingTableProps {
  chartData: ChartDataItem[]
  unit: string
}

/**
 * 排名表组件，按柱状图排序展示各模型的排名和分数。
 *
 * @param chartData - 排序后的图表数据
 * @param unit - 指标单位
 * @returns 排名表 JSX
 */
function RankingTable({ chartData, unit }: RankingTableProps): JSX.Element {
  return (
    <div className="mt-4">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            <th className="px-2 py-1 text-left">排名</th>
            <th className="px-2 py-1 text-left">模型</th>
            <th className="px-2 py-1 text-right">分数</th>
          </tr>
        </thead>
        <tbody>
          {chartData.map((item, index) => (
            <tr key={item.name} className="border-b border-border/30 text-sm">
              <td className="px-2 py-1.5">
                <span
                  className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${
                    index === 0
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : index === 1
                        ? 'bg-muted/30 text-foreground'
                        : index === 2
                          ? 'bg-amber-600/20 text-amber-500'
                          : 'text-muted-foreground'
                  }`}
                >
                  {index + 1}
                </span>
              </td>
              <td className="px-2 py-1.5 text-foreground">{item.name}</td>
              <td className="px-2 py-1.5 text-right font-mono text-foreground">
                {item.value.toFixed(2)}{unit}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * 多模型基准评测排行榜页面。
 *
 * 用户可选择多个模型和靶机，启动批量评测任务。评测过程中通过进度矩阵实时展示
 * 各模型×靶机组合的执行状态，完成后以柱状图和排名表展示通过率、代码膨胀率、
 * 平均耗时等维度的对比结果。
 *
 * @returns 排行榜页面 JSX
 */
export default function LeaderboardPage(): JSX.Element {
  const config = useAppStore((s) => s.config)

  const modelOptions = useMemo(
    () => (config ? getModelOptions(config.llm_backends) : []),
    [config]
  )
  const targetOptions = useMemo(
    () => (config ? getTargetOptions(config.targets) : []),
    [config]
  )

  if (!config) {
    return (
      <div className="flex h-full flex-col items-center justify-center">
        <h1 className="mb-4 text-3xl font-bold text-accent-cyan">模型排行榜</h1>
        <p className="text-muted-foreground">正在加载配置...</p>
      </div>
    )
  }

  return <LeaderboardPageInternal modelOptions={modelOptions} targetOptions={targetOptions} />
}
