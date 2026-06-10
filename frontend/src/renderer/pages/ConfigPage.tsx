import { useState, useCallback, useRef } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import * as Dialog from '@radix-ui/react-dialog'
import type {
  Config,
  LLMBackendConfig,
  TargetConfig,
  NormalTestConfig,
  GameRulesConfig,
  LLMBackendType,
} from '../types'
import { updateConfig, testLLM, getConfig } from '../api/client'
import { useAppStore } from '../store'

const BACKEND_TYPE_LABELS: Record<LLMBackendType, string> = {
  ollama: 'Ollama',
  openai: 'OpenAI',
  deepseek: 'DeepSeek',
  anthropic: 'Anthropic',
  mock: 'Mock',
}

const BACKEND_TYPE_COLORS: Record<LLMBackendType, string> = {
  ollama: 'bg-blue-500/20 text-blue-400',
  openai: 'bg-green-500/20 text-green-400',
  deepseek: 'bg-purple-500/20 text-purple-400',
  anthropic: 'bg-orange-500/20 text-orange-400',
  mock: 'bg-muted/30 text-muted-foreground',
}

const GAME_RULES_FIELDS: { key: keyof GameRulesConfig; label: string }[] = [
  { key: 'max_blue_retries', label: '蓝队最大重试次数' },
  { key: 'performance_degrade_limit', label: '性能退化限制' },
  { key: 'code_bloat_limit', label: '代码膨胀限制' },
  { key: 'red_strategy_mutation_threshold', label: '红队策略变异阈值' },
  { key: 'max_arena_rounds', label: '最大竞技轮数' },
  { key: 'self_adversary_attempts', label: '自我对抗尝试次数' },
  { key: 'blue_self_iteration_limit', label: '蓝队自我迭代限制' },
  { key: 'red_max_plans_early', label: '红队早期最大计划数' },
  { key: 'red_max_plans_late', label: '红队后期最大计划数' },
]

const DEFAULT_LLM_BACKEND: LLMBackendConfig = {
  backend: 'ollama',
  model: '',
  api_key: '',
  base_url: '',
  max_retries: 3,
  temperature: 0.7,
  max_tokens: 2048,
  mock_response: '',
}

const DEFAULT_TARGET: TargetConfig = {
  name: '',
  description: '',
  sandbox_type: 'process',
  sandbox_spec: {},
  code_path: '',
  code: '',
  public_spec: '',
  attack_surface: '',
  success_criteria: { attack: '', fix: '' },
  normal_tests: [],
}

const DEFAULT_NORMAL_TEST: NormalTestConfig = {
  name: '',
  input: {},
  expected_output: {},
}

const FIELD_STYLE = 'w-full rounded border bg-secondary border-border text-foreground px-3 py-2 text-sm focus:outline-none focus:border-ring focus:ring-1 focus:ring-ring'
const LABEL_STYLE = 'block text-sm font-medium text-foreground mb-1'
const PRIMARY_BTN = 'bg-primary hover:bg-primary/80 text-primary-foreground font-bold px-4 py-2 rounded text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
const DANGER_BTN = 'bg-destructive/20 text-destructive hover:bg-destructive/30 px-3 py-1.5 rounded text-sm transition-colors'
const SECONDARY_BTN = 'border border-border text-foreground hover:bg-muted px-4 py-2 rounded text-sm transition-colors'

/**
 * 保存状态提示组件。
 *
 * 根据当前保存状态显示对应的提示信息（保存中/成功/失败），空闲时不显示任何内容。
 *
 * @param status - 当前保存状态：idle | saving | success | error
 * @returns 状态提示 JSX，空闲时返回 null
 */
function SaveStatusToast({ status }: { status: 'idle' | 'saving' | 'success' | 'error' }): JSX.Element | null {
  if (status === 'idle') return null

  const config = {
    saving: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', msg: '保存中...' },
    success: { bg: 'bg-green-500/20', text: 'text-green-400', msg: '保存成功' },
    error: { bg: 'bg-red-500/20', text: 'text-red-400', msg: '保存失败' },
  }[status]

  return (
    <span className={`ml-3 rounded px-2 py-0.5 text-xs ${config.bg} ${config.text}`}>
      {config.msg}
    </span>
  )
}

interface LLMFormProps {
  initial?: LLMBackendConfig
  onSave: (config: LLMBackendConfig) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * LLM 后端配置表单弹窗组件。
 *
 * 支持添加和编辑两种模式，提供后端类型选择、模型名称、API Key、Base URL 等配置项。
 * 当选择 Mock 类型时，仅显示 Mock 响应文本输入框。
 *
 * @param initial - 编辑模式下的初始配置值，添加模式为 undefined
 * @param onSave - 表单保存回调，接收完整的 LLMBackendConfig
 * @param open - 弹窗是否打开
 * @param onOpenChange - 弹窗打开状态变更回调
 * @returns LLM 配置表单弹窗 JSX
 */
function LLMFormDialog({ initial, onSave, open, onOpenChange }: LLMFormProps): JSX.Element {
  const [form, setForm] = useState<LLMBackendConfig>(
    initial ? { ...initial } : { ...DEFAULT_LLM_BACKEND }
  )

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setForm(initial ? { ...initial } : { ...DEFAULT_LLM_BACKEND })
      }
      onOpenChange(nextOpen)
    },
    [initial, onOpenChange]
  )

  const updateField = useCallback(
    <K extends keyof LLMBackendConfig>(key: K, value: LLMBackendConfig[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }))
    },
    []
  )

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      onSave(form)
      onOpenChange(false)
    },
    [form, onSave, onOpenChange]
  )

  const isMock = form.backend === 'mock'

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 data-[state=open]:animate-fadeIn" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-6 shadow-2xl overflow-y-auto">
          <Dialog.Title className="mb-4 text-lg font-bold text-accent-cyan">
            {initial ? '编辑 LLM 后端' : '添加 LLM 后端'}
          </Dialog.Title>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className={LABEL_STYLE}>后端类型</label>
              <select
                className={FIELD_STYLE}
                value={form.backend}
                onChange={(e) => updateField('backend', e.target.value as LLMBackendType)}
              >
                {Object.entries(BACKEND_TYPE_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>

            {isMock ? (
              <div>
                <label className={LABEL_STYLE}>Mock 响应</label>
                <textarea
                  className={FIELD_STYLE}
                  rows={4}
                  value={form.mock_response}
                  onChange={(e) => updateField('mock_response', e.target.value)}
                />
              </div>
            ) : (
              <>
                <div>
                  <label className={LABEL_STYLE}>Model</label>
                  <input
                    className={FIELD_STYLE}
                    value={form.model}
                    onChange={(e) => updateField('model', e.target.value)}
                    placeholder="gpt-4o / claude-3-opus / llama3..."
                  />
                </div>

                {(form.backend === 'openai' || form.backend === 'deepseek' || form.backend === 'anthropic') && (
                  <div>
                    <label className={LABEL_STYLE}>API Key</label>
                    <input
                      className={FIELD_STYLE}
                      type="password"
                      value={form.api_key}
                      onChange={(e) => updateField('api_key', e.target.value)}
                      placeholder="sk-..."
                    />
                  </div>
                )}

                {(form.backend === 'ollama' || form.backend === 'deepseek') && (
                  <div>
                    <label className={LABEL_STYLE}>Base URL</label>
                    <input
                      className={FIELD_STYLE}
                      value={form.base_url}
                      onChange={(e) => updateField('base_url', e.target.value)}
                      placeholder={form.backend === 'ollama' ? 'http://localhost:11434' : 'https://api.deepseek.com'}
                    />
                  </div>
                )}

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className={LABEL_STYLE}>Max Retries</label>
                    <input
                      className={FIELD_STYLE}
                      type="number"
                      value={form.max_retries}
                      onChange={(e) => updateField('max_retries', Number(e.target.value))}
                    />
                  </div>
                  <div>
                    <label className={LABEL_STYLE}>Temperature</label>
                    <input
                      className={FIELD_STYLE}
                      type="number"
                      step="0.1"
                      min="0"
                      max="2"
                      value={form.temperature}
                      onChange={(e) => updateField('temperature', Number(e.target.value))}
                    />
                  </div>
                  <div>
                    <label className={LABEL_STYLE}>Max Tokens</label>
                    <input
                      className={FIELD_STYLE}
                      type="number"
                      value={form.max_tokens}
                      onChange={(e) => updateField('max_tokens', Number(e.target.value))}
                    />
                  </div>
                </div>
              </>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Dialog.Close asChild>
                <button type="button" className={SECONDARY_BTN}>取消</button>
              </Dialog.Close>
              <button type="submit" className={PRIMARY_BTN}>
                {initial ? '保存' : '添加'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

interface TargetFormProps {
  initial?: TargetConfig
  onSave: (config: TargetConfig) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * 靶机配置表单弹窗组件。
 *
 * 支持添加和编辑两种模式，提供靶机名称、沙盒类型、代码、公开规格、攻击面、
 * 成功标准以及测试用例（可增删改）等完整配置项。
 *
 * @param initial - 编辑模式下的初始配置值，添加模式为 undefined
 * @param onSave - 表单保存回调，接收完整的 TargetConfig
 * @param open - 弹窗是否打开
 * @param onOpenChange - 弹窗打开状态变更回调
 * @returns 靶机配置表单弹窗 JSX
 */
function TargetFormDialog({ initial, onSave, open, onOpenChange }: TargetFormProps): JSX.Element {
  const [form, setForm] = useState<TargetConfig>(
    initial ? { ...initial, normal_tests: initial.normal_tests.map((t) => ({ ...t })) } : { ...DEFAULT_TARGET }
  )
  const [testForm, setTestForm] = useState<NormalTestConfig>({ ...DEFAULT_NORMAL_TEST })
  const [editingTestIndex, setEditingTestIndex] = useState<number | null>(null)

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setForm(initial ? { ...initial, normal_tests: initial.normal_tests.map((t) => ({ ...t })) } : { ...DEFAULT_TARGET })
        setTestForm({ ...DEFAULT_NORMAL_TEST })
        setEditingTestIndex(null)
      }
      onOpenChange(nextOpen)
    },
    [initial, onOpenChange]
  )

  const updateField = useCallback(
    <K extends keyof TargetConfig>(key: K, value: TargetConfig[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }))
    },
    []
  )

  const updateSuccessCriteria = useCallback((key: 'attack' | 'fix', value: string) => {
    setForm((prev) => ({
      ...prev,
      success_criteria: { ...prev.success_criteria, [key]: value },
    }))
  }, [])

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      onSave(form)
      onOpenChange(false)
    },
    [form, onSave, onOpenChange]
  )

  const addOrUpdateTest = useCallback(() => {
    if (!testForm.name.trim()) return
    setForm((prev) => {
      const tests = [...prev.normal_tests]
      if (editingTestIndex !== null) {
        tests[editingTestIndex] = { ...testForm }
      } else {
        tests.push({ ...testForm })
      }
      return { ...prev, normal_tests: tests }
    })
    setTestForm({ ...DEFAULT_NORMAL_TEST })
    setEditingTestIndex(null)
  }, [testForm, editingTestIndex])

  const editTest = useCallback(
    (index: number) => {
      setTestForm({ ...form.normal_tests[index] })
      setEditingTestIndex(index)
    },
    [form.normal_tests]
  )

  const removeTest = useCallback((index: number) => {
    setForm((prev) => ({
      ...prev,
      normal_tests: prev.normal_tests.filter((_, i) => i !== index),
    }))
    if (editingTestIndex === index) {
      setTestForm({ ...DEFAULT_NORMAL_TEST })
      setEditingTestIndex(null)
    }
  }, [editingTestIndex])

  const formatJSON = useCallback((value: Record<string, unknown>): string => {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return '{}'
    }
  }, [])

  const parseJSONField = useCallback((raw: string): Record<string, unknown> => {
    try {
      const parsed = JSON.parse(raw)
      return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}
    } catch {
      return {}
    }
  }, [])

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 data-[state=open]:animate-fadeIn" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-6 shadow-2xl overflow-y-auto">
          <Dialog.Title className="mb-4 text-lg font-bold text-accent-cyan">
            {initial ? '编辑靶机' : '添加靶机'}
          </Dialog.Title>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={LABEL_STYLE}>名称</label>
                <input className={FIELD_STYLE} value={form.name} onChange={(e) => updateField('name', e.target.value)} />
              </div>
              <div>
                <label className={LABEL_STYLE}>Sandbox 类型</label>
                <select className={FIELD_STYLE} value={form.sandbox_type} onChange={(e) => updateField('sandbox_type', e.target.value as 'process' | 'docker')}>
                  <option value="process">Process</option>
                  <option value="docker">Docker</option>
                </select>
              </div>
            </div>

            <div>
              <label className={LABEL_STYLE}>描述</label>
              <textarea className={FIELD_STYLE} rows={2} value={form.description} onChange={(e) => updateField('description', e.target.value)} />
            </div>
            <div>
              <label className={LABEL_STYLE}>代码路径</label>
              <input className={FIELD_STYLE} value={form.code_path} onChange={(e) => updateField('code_path', e.target.value)} />
            </div>
            <div>
              <label className={LABEL_STYLE}>代码</label>
              <textarea className={FIELD_STYLE} rows={4} value={form.code} onChange={(e) => updateField('code', e.target.value)} />
            </div>
            <div>
              <label className={LABEL_STYLE}>公开规格</label>
              <textarea className={FIELD_STYLE} rows={3} value={form.public_spec} onChange={(e) => updateField('public_spec', e.target.value)} />
            </div>
            <div>
              <label className={LABEL_STYLE}>攻击面</label>
              <textarea className={FIELD_STYLE} rows={3} value={form.attack_surface} onChange={(e) => updateField('attack_surface', e.target.value)} />
            </div>

            <div className="border-t border-border pt-4">
              <h3 className="mb-2 text-sm font-semibold text-foreground">成功标准</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={LABEL_STYLE}>攻击成功标准</label>
                  <textarea className={FIELD_STYLE} rows={2} value={form.success_criteria.attack} onChange={(e) => updateSuccessCriteria('attack', e.target.value)} />
                </div>
                <div>
                  <label className={LABEL_STYLE}>修复成功标准</label>
                  <textarea className={FIELD_STYLE} rows={2} value={form.success_criteria.fix} onChange={(e) => updateSuccessCriteria('fix', e.target.value)} />
                </div>
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-foreground">测试用例</h3>
                <span className="text-xs text-muted-foreground">{form.normal_tests.length} 个</span>
              </div>

              <div className="mb-3 space-y-2">
                {form.normal_tests.map((test, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded border border-border bg-secondary px-3 py-2"
                  >
                    <span className="text-sm text-foreground">{test.name}</span>
                    <div className="flex gap-2">
                      <button type="button" onClick={() => editTest(idx)} className="text-xs text-accent-cyan hover:text-accent-cyan/80">
                        编辑
                      </button>
                      <button type="button" onClick={() => removeTest(idx)} className="text-xs text-destructive hover:text-destructive/80">
                        删除
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="rounded border border-border bg-secondary p-3 space-y-3">
                <input
                  className={FIELD_STYLE}
                  placeholder="测试名称"
                  value={testForm.name}
                  onChange={(e) => setTestForm((prev) => ({ ...prev, name: e.target.value }))}
                />
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">输入 (JSON)</label>
                  <textarea
                    className={FIELD_STYLE}
                    rows={3}
                    value={formatJSON(testForm.input)}
                    onChange={(e) => setTestForm((prev) => ({ ...prev, input: parseJSONField(e.target.value) }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-muted-foreground">预期输出 (JSON)</label>
                  <textarea
                    className={FIELD_STYLE}
                    rows={3}
                    value={formatJSON(testForm.expected_output)}
                    onChange={(e) => setTestForm((prev) => ({ ...prev, expected_output: parseJSONField(e.target.value) }))}
                  />
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={addOrUpdateTest} className={PRIMARY_BTN}>
                    {editingTestIndex !== null ? '更新测试用例' : '添加测试用例'}
                  </button>
                  {editingTestIndex !== null && (
                    <button type="button" onClick={() => { setTestForm({ ...DEFAULT_NORMAL_TEST }); setEditingTestIndex(null) }} className={SECONDARY_BTN}>
                      取消编辑
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Dialog.Close asChild>
                <button type="button" className={SECONDARY_BTN}>取消</button>
              </Dialog.Close>
              <button type="submit" className={PRIMARY_BTN}>
                {initial ? '保存' : '添加'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export default function ConfigPage(): JSX.Element {
  const storeConfig = useAppStore((s) => s.config)
  const setStoreConfig = useAppStore((s) => s.setConfig)
  const [config, setConfig] = useState<Config | null>(storeConfig)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [activeTab, setActiveTab] = useState('llm')

  const [llmDialogOpen, setLlmDialogOpen] = useState(false)
  const [editingLlmIndex, setEditingLlmIndex] = useState<number | null>(null)
  const [targetDialogOpen, setTargetDialogOpen] = useState(false)
  const [editingTargetIndex, setEditingTargetIndex] = useState<number | null>(null)
  const [testResults, setTestResults] = useState<Record<number, { ok: boolean; message: string } | null>>({})
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  /**
   * 从后端加载最新配置并同步到本地状态和全局 store。
   */
  const loadConfig = useCallback(async () => {
    try {
      const cfg = await getConfig()
      setConfig(cfg)
      setStoreConfig(cfg)
    } catch {
      if (storeConfig) {
        setConfig(storeConfig)
      }
    }
  }, [storeConfig, setStoreConfig])

  const handleSave = useCallback(async () => {
    if (!config) return
    setSaveStatus('saving')
    try {
      const saved = await updateConfig(config)
      setConfig(saved)
      setStoreConfig(saved)
      setSaveStatus('success')
    } catch {
      setSaveStatus('error')
    }
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => setSaveStatus('idle'), 3000)
  }, [config, setStoreConfig])

  /**
   * 向本地配置中添加一个新的 LLM 后端。
   *
   * @param backend - 待添加的 LLM 后端配置
   */
  const handleAddLLM = useCallback((backend: LLMBackendConfig) => {
    setConfig((prev) => prev ? { ...prev, llm_backends: [...prev.llm_backends, backend] } : prev)
    setEditingLlmIndex(null)
  }, [])

  const handleEditLLM = useCallback((index: number, backend: LLMBackendConfig) => {
    setConfig((prev) => {
      if (!prev) return prev
      const backends = [...prev.llm_backends]
      backends[index] = backend
      return { ...prev, llm_backends: backends }
    })
    setEditingLlmIndex(null)
  }, [])

  const handleDeleteLLM = useCallback((index: number) => {
    setConfig((prev) => {
      if (!prev) return prev
      return { ...prev, llm_backends: prev.llm_backends.filter((_, i) => i !== index) }
    })
  }, [])

  const openAddLLMDialog = useCallback(() => {
    setEditingLlmIndex(null)
    setLlmDialogOpen(true)
  }, [])

  const openEditLLMDialog = useCallback((index: number) => {
    setEditingLlmIndex(index)
    setLlmDialogOpen(true)
  }, [])

  /**
   * 对指定索引位置的 LLM 后端发起连接测试请求，并显示测试结果。
   *
   * @param index - 要测试的后端在 llm_backends 数组中的索引
   */
  const handleTestLLM = useCallback(async (index: number) => {
    if (!config) return
    const backend = config.llm_backends[index]
    try {
      const result = await testLLM(backend)
      setTestResults((prev) => ({ ...prev, [index]: result }))
    } catch {
      setTestResults((prev) => ({ ...prev, [index]: { ok: false, message: '连接测试失败' } }))
    }
  }, [config])

  const handleAddTarget = useCallback((target: TargetConfig) => {
    setConfig((prev) => prev ? { ...prev, targets: [...prev.targets, target] } : prev)
    setEditingTargetIndex(null)
  }, [])

  /**
   * 更新本地配置中指定索引位置的靶机。
   *
   * @param index - 要编辑的靶机在 targets 数组中的索引
   * @param target - 更新后的靶机配置
   */
  const handleEditTarget = useCallback((index: number, target: TargetConfig) => {
    setConfig((prev) => {
      if (!prev) return prev
      const targets = [...prev.targets]
      targets[index] = target
      return { ...prev, targets }
    })
    setEditingTargetIndex(null)
  }, [])

  /**
   * 从本地配置中删除指定索引位置的靶机。
   *
   * @param index - 要删除的靶机在 targets 数组中的索引
   */
  const handleDeleteTarget = useCallback((index: number) => {
    setConfig((prev) => {
      if (!prev) return prev
      return { ...prev, targets: prev.targets.filter((_, i) => i !== index) }
    })
  }, [])

  const openAddTargetDialog = useCallback(() => {
    setEditingTargetIndex(null)
    setTargetDialogOpen(true)
  }, [])

  const openEditTargetDialog = useCallback((index: number) => {
    setEditingTargetIndex(index)
    setTargetDialogOpen(true)
  }, [])

  /**
   * 更新本地配置中游戏规则参数的单个字段值。
   *
   * @param key - 要更新的游戏规则字段名
   * @param value - 新的数值
   */
  const updateGameRule = useCallback(<K extends keyof GameRulesConfig>(key: K, value: number) => {
    setConfig((prev) => {
      if (!prev) return prev
      return { ...prev, game_rules: { ...prev.game_rules, [key]: value } }
    })
  }, [])

  if (!config) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">配置未加载</p>
        <button onClick={loadConfig} className={PRIMARY_BTN}>
          加载配置
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-accent-cyan">配置管理</h1>
        <div className="flex items-center gap-3">
          <button onClick={loadConfig} className={SECONDARY_BTN}>
            重新加载
          </button>
          <button onClick={handleSave} disabled={saveStatus === 'saving'} className={PRIMARY_BTN}>
            保存配置
          </button>
          <SaveStatusToast status={saveStatus} />
        </div>
      </div>

      <Tabs.Root value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <Tabs.List className="mb-6 flex gap-1 rounded-lg bg-secondary p-1">
          {(['llm', 'targets', 'rules'] as const).map((tab) => {
            const label = { llm: 'LLM 后端', targets: '靶机管理', rules: '游戏规则' }[tab]
            return (
              <Tabs.Trigger
                key={tab}
                value={tab}
                className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                  activeTab === tab
                    ? 'bg-accent-cyan/20 text-accent-cyan'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {label}
              </Tabs.Trigger>
            )
          })}
        </Tabs.List>

        <Tabs.Content value="llm" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-foreground">
              LLM 后端列表
              <span className="ml-2 text-sm text-muted-foreground">
                ({config.llm_backends.length})
              </span>
            </h2>
            <button onClick={openAddLLMDialog} className={PRIMARY_BTN}>
              + 添加后端
            </button>
          </div>

          {config.llm_backends.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border py-12 text-center text-muted-foreground">
              暂无 LLM 后端配置，点击&quot;添加后端&quot;开始
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {config.llm_backends.map((backend, idx) => {
                const testResult = testResults[idx]
                return (
                  <div
                    key={`${backend.backend}-${backend.model}-${idx}`}
                    className="rounded-lg border border-border bg-card p-4"
                  >
                    <div className="mb-3 flex items-start justify-between">
                      <div>
                        <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${BACKEND_TYPE_COLORS[backend.backend]}`}>
                          {BACKEND_TYPE_LABELS[backend.backend]}
                        </span>
                        {backend.model && (
                          <span className="ml-2 text-sm text-foreground">{backend.model}</span>
                        )}
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => openEditLLMDialog(idx)} className="text-xs text-accent-cyan hover:text-accent-cyan/80">
                          编辑
                        </button>
                        <button onClick={() => handleDeleteLLM(idx)} className="text-xs text-destructive hover:text-destructive/80">
                          删除
                        </button>
                      </div>
                    </div>

                    {backend.base_url && (
                      <p className="mb-2 text-xs text-muted-foreground truncate">{backend.base_url}</p>
                    )}

                    <div className="mb-3 flex gap-4 text-xs text-muted-foreground/70">
                      <span>重试: {backend.max_retries}</span>
                      <span>温度: {backend.temperature}</span>
                      <span>Tokens: {backend.max_tokens}</span>
                    </div>

                    {testResult && (
                      <div
                        className={`mb-3 rounded px-3 py-2 text-xs ${
                          testResult.ok
                            ? 'bg-green-500/10 text-green-400'
                            : 'bg-red-500/10 text-red-400'
                        }`}
                      >
                        {testResult.message}
                      </div>
                    )}

                    <button
                      onClick={() => handleTestLLM(idx)}
                      className="w-full rounded bg-secondary px-3 py-1.5 text-xs text-muted-foreground hover:bg-secondary/80 hover:text-foreground transition-colors"
                    >
                      测试连接
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </Tabs.Content>

        <Tabs.Content value="targets" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-foreground">
              靶机列表
              <span className="ml-2 text-sm text-muted-foreground">
                ({config.targets.length})
              </span>
            </h2>
            <button onClick={openAddTargetDialog} className={PRIMARY_BTN}>
              + 添加靶机
            </button>
          </div>

          {config.targets.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border py-12 text-center text-muted-foreground">
              暂无靶机配置，点击&quot;添加靶机&quot;开始
            </div>
          ) : (
            <div className="space-y-3">
              {config.targets.map((target, idx) => (
                <div
                  key={`${target.name}-${idx}`}
                  className="rounded-lg border border-border bg-card p-4"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">{target.name}</h3>
                      <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{target.description}</p>
                      <span className="mt-2 inline-block text-xs text-muted-foreground/70">
                        {target.normal_tests.length} 个测试用例
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => openEditTargetDialog(idx)} className="text-xs text-accent-cyan hover:text-accent-cyan/80">
                        编辑
                      </button>
                      <button onClick={() => handleDeleteTarget(idx)} className={DANGER_BTN}>
                        删除
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Tabs.Content>

        <Tabs.Content value="rules" className="space-y-4">
          <h2 className="text-lg font-semibold text-foreground">游戏规则参数</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {GAME_RULES_FIELDS.map(({ key, label }) => (
              <div key={key}>
                <label className={LABEL_STYLE}>{label}</label>
                <input
                  className={FIELD_STYLE}
                  type="number"
                  value={config.game_rules[key]}
                  onChange={(e) => updateGameRule(key, Number(e.target.value))}
                />
              </div>
            ))}
          </div>
        </Tabs.Content>
      </Tabs.Root>

      <LLMFormDialog
        open={llmDialogOpen}
        onOpenChange={setLlmDialogOpen}
        initial={editingLlmIndex !== null ? config.llm_backends[editingLlmIndex] : undefined}
        onSave={editingLlmIndex !== null ? (b) => handleEditLLM(editingLlmIndex, b) : handleAddLLM}
      />

      <TargetFormDialog
        open={targetDialogOpen}
        onOpenChange={setTargetDialogOpen}
        initial={editingTargetIndex !== null ? config.targets[editingTargetIndex] : undefined}
        onSave={editingTargetIndex !== null ? (t) => handleEditTarget(editingTargetIndex, t) : handleAddTarget}
      />
    </div>
  )
}
