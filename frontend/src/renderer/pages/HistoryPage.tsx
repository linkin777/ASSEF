import { useState, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppStore } from '../store'
import { getHistoryList, getHistoryDetail, deleteHistory } from '../api/client'
import type { HistoryRecordSummary, HistoryTypeFilter } from '../types'

const TYPE_OPTIONS: { key: HistoryTypeFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'arena', label: '竞技场' },
  { key: 'benchmark', label: '排行榜' },
]

const PAGE_SIZE = 20

export default function HistoryPage(): JSX.Element {
  const {
    historyRecords,
    historyTotal,
    historyPage,
    historyTypeFilter,
    historyLoading,
    setHistoryRecords,
    setHistoryTypeFilter,
    setHistoryLoading,
  } = useAppStore()

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const totalPages = Math.max(1, Math.ceil(historyTotal / PAGE_SIZE))

  const loadRecords = useCallback(async (page: number, typeFilter: HistoryTypeFilter) => {
    setHistoryLoading(true)
    try {
      const typeParam = typeFilter === 'all' ? undefined : typeFilter
      const res = await getHistoryList(typeParam, page, PAGE_SIZE)
      setHistoryRecords(res.items, res.total, res.page)
    } catch {
      setHistoryRecords([], 0, page)
    } finally {
      setHistoryLoading(false)
    }
  }, [setHistoryRecords, setHistoryLoading])

  useEffect(() => {
    loadRecords(historyPage, historyTypeFilter)
  }, []) 

  useEffect(() => {
    loadRecords(historyPage, historyTypeFilter)
  }, [historyPage, historyTypeFilter])

  const handleTypeChange = useCallback((type: HistoryTypeFilter) => {
    setHistoryTypeFilter(type)
    setExpandedId(null)
    setDetailData(null)
  }, [setHistoryTypeFilter])

  const handlePageChange = useCallback((page: number) => {
    setHistoryRecords([], historyTotal, page)
    setExpandedId(null)
    setDetailData(null)
  }, [setHistoryRecords, historyTotal])

  const handleToggleExpand = useCallback(async (recordId: string) => {
    if (expandedId === recordId) {
      setExpandedId(null)
      setDetailData(null)
      return
    }
    setExpandedId(recordId)
    setDetailLoading(true)
    setDetailData(null)
    try {
      const data = await getHistoryDetail(recordId)
      setDetailData(data)
    } catch {
      setDetailData(null)
    } finally {
      setDetailLoading(false)
    }
  }, [expandedId])

  const handleDelete = useCallback(async (recordId: string) => {
    if (!window.confirm(`确定删除记录 ${recordId}？`)) return
    setDeletingId(recordId)
    try {
      await deleteHistory(recordId)
      setExpandedId(null)
      setDetailData(null)
      loadRecords(historyPage, historyTypeFilter)
    } catch {
    } finally {
      setDeletingId(null)
    }
  }, [historyPage, historyTypeFilter, loadRecords])

  const formatTime = (ts: string) => {
    if (!ts) return ''
    if (ts.length === 15 && ts.includes('_')) {
      const parts = ts.split('_')
      const date = parts[0]
      const time = parts[1]
      return `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)} ${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`
    }
    try {
      return new Date(ts).toLocaleString('zh-CN')
    } catch {
      return ts
    }
  }

  const renderArenaDetail = (data: Record<string, unknown>) => {
    const rounds = data.rounds as Array<Record<string, unknown>> | undefined
    if (!rounds || rounds.length === 0) return <p className="text-muted-foreground text-sm">无回合数据</p>
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-2 px-2">回合</th>
              <th className="py-2 px-2">红队成功</th>
              <th className="py-2 px-2">蓝队通过</th>
              <th className="py-2 px-2">cost</th>
              <th className="py-2 px-2">蓝队重试</th>
              <th className="py-2 px-2">eval</th>
            </tr>
          </thead>
          <tbody>
            {rounds.map((r, i) => {
              const evalParts: string[] = []
              if (r.eval_red) evalParts.push('R')
              if (r.eval_yellow) evalParts.push('Y')
              if (r.eval_green) evalParts.push('G')

              return (
                <tr key={i} className="border-b border-border hover:bg-card/30">
                  <td className="py-2 px-2 text-accent-cyan">{String(r.round_num)}</td>
                  <td className="py-2 px-2">
                    {r.attack_success
                      ? <span className="text-red-400">成功</span>
                      : <span className="text-muted-foreground">失败</span>}
                  </td>
                  <td className="py-2 px-2">
                    {r.defense_passed
                      ? <span className="text-green-400">通过</span>
                      : r.defense_code != null
                        ? <span className="text-red-400">未通过</span>
                        : <span className="text-muted-foreground/70">—</span>}
                  </td>
                  <td className="py-2 px-2">{Number(r.cost_score).toFixed(3)}</td>
                  <td className="py-2 px-2">{String(r.blue_retries ?? 0)}</td>
                  <td className="py-2 px-2 font-mono text-xs">{evalParts.join(' ') || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }

  const renderBenchmarkDetail = (data: Record<string, unknown>) => {
    const results = data.results as Array<Record<string, unknown>> | undefined
    if (!results || results.length === 0) return <p className="text-muted-foreground text-sm">无评测数据</p>
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-2 px-2">靶机</th>
              <th className="py-2 px-2">模型</th>
              <th className="py-2 px-2">通过率</th>
              <th className="py-2 px-2">膨胀率</th>
              <th className="py-2 px-2">耗时(s)</th>
            </tr>
          </thead>
          <tbody>
            {results.flatMap((r) => {
              const scores = r.scores as Array<Record<string, unknown>> | undefined
              const targetName = String(r.target_name ?? '')
              if (!scores) return null
              return scores.map((s, j) => (
                <tr key={`${r.target_name}-${j}`} className="border-b border-border hover:bg-card/30">
                  <td className="py-2 px-2 text-accent-cyan">{targetName}</td>
                  <td className="py-2 px-2">{String(s.model_name ?? '')}</td>
                  <td className="py-2 px-2">
                    <span className={Number(s.fix_pass_rate) >= 0.8 ? 'text-green-400' : Number(s.fix_pass_rate) >= 0.5 ? 'text-yellow-400' : 'text-red-400'}>
                      {(Number(s.fix_pass_rate) * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2 px-2">{(Number(s.code_bloat_ratio)).toFixed(2)}x</td>
                  <td className="py-2 px-2">{Number(s.avg_time_seconds).toFixed(2)}</td>
                </tr>
              ))
            }).filter(Boolean)}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">历史记录</h1>
        <p className="mt-1 text-sm text-muted-foreground">查看过往的竞技场对抗与排行榜评测结果</p>
      </div>

      <div className="mb-4 flex items-center gap-2">
        {TYPE_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            onClick={() => handleTypeChange(opt.key)}
            className={`rounded-md px-4 py-1.5 text-sm transition-all duration-150 ${
              historyTypeFilter === opt.key
                ? 'bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/30'
                : 'bg-card text-muted-foreground border border-transparent hover:bg-muted hover:text-foreground'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {historyLoading && historyRecords.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      ) : historyRecords.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-muted-foreground">暂无历史记录</p>
        </div>
      ) : (
        <div className="flex-1 overflow-auto space-y-3">
          <AnimatePresence>
            {historyRecords.map((record) => {
              const isExpanded = expandedId === record.record_id
              const isDeleting = deletingId === record.record_id
              const isArena = record.record_type === 'arena'

              return (
                <motion.div
                  key={record.record_id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="rounded-lg border border-border bg-secondary overflow-hidden"
                >
                  <button
                    onClick={() => handleToggleExpand(record.record_id)}
                    className="w-full px-5 py-4 text-left hover:bg-card/30 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                          isArena ? 'bg-destructive/15 text-destructive' : 'bg-purple-500/15 text-purple-400'
                        }`}>
                          {isArena ? '竞技场' : '排行榜'}
                        </span>
                        <span className="text-foreground font-medium">
                          {isArena ? record.target_name : (record.target_names || []).join(', ')}
                        </span>
                      </div>
                      <div className="flex items-center gap-4">
                        {isArena ? (
                          <span className="text-xs text-muted-foreground">
                            红 <span className="text-red-400 font-mono">{record.red_score?.toFixed(1)}</span>
                            {' : '}
                            蓝 <span className="text-green-400 font-mono">{record.blue_score?.toFixed(1)}</span>
                            {' | '}
                            {record.total_rounds} 回合
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {record.target_names?.length || 0} 靶机 × {record.model_names?.length || 0} 模型
                          </span>
                        )}
                        <span className="text-xs text-muted-foreground/70">
                          {formatTime(record.created_at)}
                        </span>
                        <span className={`text-muted-foreground transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                          ▼
                        </span>
                      </div>
                    </div>
                  </button>

                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="border-t border-border px-5 py-4">
                          {detailLoading ? (
                            <div className="flex items-center justify-center py-8">
                              <p className="text-muted-foreground text-sm">加载详情中...</p>
                            </div>
                          ) : detailData ? (
                            <>
                              {detailData.record_type === 'arena'
                                ? renderArenaDetail(detailData)
                                : renderBenchmarkDetail(detailData)}
                            </>
                          ) : (
                            <p className="text-muted-foreground text-sm">加载失败</p>
                          )}

                          <div className="mt-4 flex justify-end border-t border-border pt-3">
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDelete(record.record_id)
                              }}
                              disabled={isDeleting}
                              className="rounded-md px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
                            >
                              {isDeleting ? '删除中...' : '删除记录'}
                            </button>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              )
            })}
          </AnimatePresence>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 py-4">
              <button
                onClick={() => handlePageChange(historyPage - 1)}
                disabled={historyPage <= 1}
                className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-card disabled:opacity-30 disabled:cursor-not-allowed"
              >
                上一页
              </button>
              <span className="text-sm text-muted-foreground">
                {historyPage} / {totalPages}
              </span>
              <button
                onClick={() => handlePageChange(historyPage + 1)}
                disabled={historyPage >= totalPages}
                className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-card disabled:opacity-30 disabled:cursor-not-allowed"
              >
                下一页
              </button>
            </div>
          )}
        </div>
      )}

      {historyLoading && historyRecords.length > 0 && (
        <div className="flex justify-center py-2">
          <span className="text-xs text-muted-foreground/70">刷新中...</span>
        </div>
      )}
    </div>
  )
}
