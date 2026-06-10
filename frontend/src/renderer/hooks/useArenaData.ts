import { useMemo } from 'react'
import type { ProgressEvent, Config, TargetConfig } from '../types'

// ============================================================
// 接口定义
// ============================================================

export interface DiffLine {
  type: 'same' | 'added' | 'removed' | 'changed'
  original: string
  fixed: string
}

export interface DefenseDataPoint {
  round: number
  rate: number
}

export interface CodeVersion {
  round: number
  code: string
  timestamp: number
}

export interface TestResultItem {
  id: number
  round: number
  name: string
  input: string
  expectedOutput: string
  actualOutput: string
  passed: boolean
  reason: string
}

export interface AttackScriptRound {
  round: number
  script: string
}

export interface RoundInfo {
  round: number
  attackSuccess: boolean
  defensePassed: boolean
  attackScript: string
  testResults: TestResultItem[]
  fixedCode: string
  scoreRed: number
  scoreBlue: number
  blueIterations: number
  blueMode: 'fix' | 'enhance' | ''
  costScore: number
}

// ============================================================
// 工具函数
// ============================================================

export function safeNumber(data: Record<string, unknown>, key: string, fallback = 0): number {
  const v = data[key]
  return typeof v === 'number' ? v : fallback
}

export function safeString(data: Record<string, unknown>, key: string, fallback = ''): string {
  const v = data[key]
  return typeof v === 'string' ? v : fallback
}

export function safeBool(data: Record<string, unknown>, key: string, fallback = false): boolean {
  const v = data[key]
  return typeof v === 'boolean' ? v : fallback
}

/**
 * 逐行比较原始代码和修复后的代码，生成 Diff 行数组。
 * 每行标记为 same（相同）、added（新增）、removed（删除）或 changed（修改）。
 *
 * @param original - 原始代码
 * @param fixed - 修复后的代码
 * @returns Diff 行数组，每项包含类型、原始行内容和修复行内容
 */
export function computeDiff(original: string, fixed: string): DiffLine[] {
  const origLines = original.split('\n')
  const fixedLines = fixed.split('\n')
  const maxLen = Math.max(origLines.length, fixedLines.length)
  const result: DiffLine[] = []

  for (let i = 0; i < maxLen; i++) {
    const o = origLines[i] ?? ''
    const f = fixedLines[i] ?? ''
    if (o === '' && f === '') {
      continue
    }
    if (o !== f) {
      if (o === '') {
        result.push({ type: 'added', original: '', fixed: f })
      } else if (f === '') {
        result.push({ type: 'removed', original: o, fixed: '' })
      } else {
        result.push({ type: 'changed', original: o, fixed: f })
      }
    } else {
      result.push({ type: 'same', original: o, fixed: f })
    }
  }

  return result
}

export function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// ============================================================
// Hook 返回值类型
// ============================================================

export interface ArenaDerivedData {
  redScore: number
  blueScore: number
  currentRound: number
  judgeScript: string
  defenseData: DefenseDataPoint[]
  allTestResults: TestResultItem[]
  attackScriptRounds: AttackScriptRound[]
  roundInfos: RoundInfo[]
  sandboxLogs: ProgressEvent[]
  originalCode: string
  targetCodeSummary: string
  redStreamText: string
  blueStreamText: string
  judgeStreamText: string
  fixedCodeVersions: CodeVersion[]
  latestFixedCode: string
}

// ============================================================
// useArenaData Hook
// ============================================================

export function useArenaData(
  progressEvents: ProgressEvent[],
  config: Config | null,
  selectedTarget: TargetConfig | null
): ArenaDerivedData {
  const originalCode = useMemo(() => {
    const intro = progressEvents
      .filter((e) => e.type === 'info' && e.step_name === 'constitution_intro')
      .at(-1)
    if (intro) {
      const code = safeString(intro.data, 'target_code', '')
      if (code) return code
    }
    if (!selectedTarget) return ''
    return selectedTarget.code
  }, [progressEvents, selectedTarget])

  const redStreamText = useMemo(() => {
    const last = progressEvents
      .filter((e) => e.type === 'step_done' && e.role === 'red_team' && e.step_name === 'generate_attack')
      .at(-1)
    if (!last) return ''
    return safeString(last.data, 'raw_response', '')
  }, [progressEvents])

  const blueStreamText = useMemo(() => {
    const tokens = progressEvents
      .filter((e) => e.type === 'llm_token' && e.role === 'blue_team')
      .reduce((acc, e) => acc + e.content, '')
    if (tokens) return tokens
    const last = progressEvents
      .filter((e) => e.type === 'step_done' && e.role === 'blue_team' && (e.step_name === 'generate_fix' || e.step_name === 'generate_enhance'))
      .at(-1)
    return last ? safeString(last.data, 'raw_response', '') : ''
  }, [progressEvents])

  const judgeStreamText = useMemo(() => {
    return progressEvents
      .filter((e) => e.type === 'llm_token' && e.role === 'judge')
      .reduce((acc, e) => acc + e.content, '')
  }, [progressEvents])

  const fixedCodeVersions = useMemo(() => {
    return progressEvents
      .filter((e) => e.type === 'step_done' && (e.step_name === 'generate_fix' || e.step_name === 'generate_enhance'))
      .map((e) => ({
        round: safeNumber(e.data, 'round', 0),
        code: safeString(e.data, 'fixed_code', ''),
        timestamp: e.timestamp,
      }))
      .filter((v) => v.code.length > 0)
  }, [progressEvents])

  const latestFixedCode = useMemo(() => {
    const last = fixedCodeVersions.at(-1)
    return last ? last.code : ''
  }, [fixedCodeVersions])

  const redScore = useMemo(() => {
    const scoreEvents = progressEvents.filter((e) => e.type === 'score_update')
    if (scoreEvents.length > 0) {
      const last = scoreEvents.at(-1)!
      return safeNumber(last.data, 'red_score', 0)
    }
    const done = progressEvents
      .filter((e) => e.type === 'task_done')
      .at(-1)
    if (done?.data?.result && typeof done.data.result === 'object') {
      const r = done.data.result as Record<string, unknown>
      return safeNumber(r, 'red_score', 0)
    }
    return 0
  }, [progressEvents])

  const blueScore = useMemo(() => {
    const scoreEvents = progressEvents.filter((e) => e.type === 'score_update')
    if (scoreEvents.length > 0) {
      const last = scoreEvents.at(-1)!
      return safeNumber(last.data, 'blue_score', 0)
    }
    const done = progressEvents
      .filter((e) => e.type === 'task_done')
      .at(-1)
    if (done?.data?.result && typeof done.data.result === 'object') {
      const r = done.data.result as Record<string, unknown>
      return safeNumber(r, 'blue_score', 0)
    }
    return 0
  }, [progressEvents])

  const currentRound = useMemo(() => {
    const rounds = progressEvents
      .filter((e) => e.type === 'step_start' && e.step_name === 'round')
    return rounds.length
  }, [progressEvents])

  const judgeScript = useMemo(() => {
    const last = progressEvents
      .filter((e) => e.type === 'info' && e.step_name === 'judge_script_ready')
      .at(-1)
    return last ? safeString(last.data, 'script_content', '') : ''
  }, [progressEvents])

  const defenseData: DefenseDataPoint[] = useMemo(() => {
    const results = progressEvents.filter((e) => e.type === 'judge_test_result')
    if (results.length === 0) return []
    const accumulated: DefenseDataPoint[] = []
    let cumPassed = 0
    results.forEach((e, idx) => {
      if (safeBool(e.data, 'passed', false)) cumPassed++
      accumulated.push({
        round: safeNumber(e.data, 'round', idx + 1),
        rate: Math.round((cumPassed / (idx + 1)) * 100),
      })
    })
    return accumulated
  }, [progressEvents])

  const allTestResults: TestResultItem[] = useMemo(() => {
    return progressEvents
      .filter((e) => e.type === 'judge_test_result')
      .map((e, i) => ({
        id: i,
        round: safeNumber(e.data, 'round', 0),
        name: safeString(e.data, 'test_name', `测试 ${i + 1}`),
        input: safeString(e.data, 'input', ''),
        expectedOutput: safeString(e.data, 'expected_output', ''),
        actualOutput: safeString(e.data, 'actual_output', ''),
        passed: safeBool(e.data, 'passed', false),
        reason: safeString(e.data, 'reason', ''),
      }))
  }, [progressEvents])

  const attackScriptRounds: AttackScriptRound[] = useMemo(() => {
    return progressEvents
      .filter((e) => e.type === 'step_done' && e.role === 'red_team' && e.step_name === 'generate_attack')
      .map((e) => ({
        round: safeNumber(e.data, 'round', 0),
        script: safeString(e.data, 'content', '') || safeString(e.data, 'raw_response', ''),
      }))
      .filter((r) => r.round > 0 && r.script.length > 0)
  }, [progressEvents])

  const roundInfos: RoundInfo[] = useMemo(() => {
    const scoreUpdates = progressEvents.filter((e) => e.type === 'score_update')
    const rounds: RoundInfo[] = []
    const scoreMap = new Map<number, { attackSuccess: boolean; defensePassed: boolean; scoreRed: number; scoreBlue: number; costScore: number }>()

    scoreUpdates.forEach((e) => {
      const r = safeNumber(e.data, 'round', 0)
      if (r > 0) {
        scoreMap.set(r, {
          attackSuccess: safeBool(e.data, 'attack_success', false),
          defensePassed: safeBool(e.data, 'defense_passed', false),
          scoreRed: safeNumber(e.data, 'red_score', 0),
          scoreBlue: safeNumber(e.data, 'blue_score', 0),
          costScore: safeNumber(e.data, 'cost_score', 0),
        })
      }
    })

    const blueIterMap = new Map<number, number>()
    const blueModeMap = new Map<number, 'fix' | 'enhance' | ''>()
    progressEvents
      .filter((e) => e.type === 'step_done' && e.role === 'blue_team' && (e.step_name === 'generate_fix' || e.step_name === 'generate_enhance'))
      .forEach((e) => {
        const r = safeNumber(e.data, 'round', 0)
        if (r > 0) {
          blueIterMap.set(r, (blueIterMap.get(r) ?? 0) + 1)
          const mode = safeString(e.data, 'mode', '')
          if (mode === 'fix' || mode === 'enhance') {
            blueModeMap.set(r, mode)
          }
        }
      })

    const maxR = currentRound
    for (let r = 1; r <= maxR; r++) {
      const score = scoreMap.get(r)
      const attackScript = attackScriptRounds.find((a) => a.round === r)?.script ?? ''
      rounds.push({
        round: r,
        attackSuccess: score?.attackSuccess ?? false,
        defensePassed: score?.defensePassed ?? false,
        attackScript,
        testResults: allTestResults.filter((t) => t.round === r),
        fixedCode: fixedCodeVersions.find((v) => v.round === r)?.code ?? '',
        scoreRed: score?.scoreRed ?? 0,
        scoreBlue: score?.scoreBlue ?? 0,
        blueIterations: blueIterMap.get(r) ?? 0,
        blueMode: blueModeMap.get(r) ?? '',
        costScore: score?.costScore ?? 0,
      })
    }

    return rounds
  }, [progressEvents, currentRound, allTestResults, fixedCodeVersions, attackScriptRounds])

  const sandboxLogs = useMemo(() => {
    return progressEvents.filter(
      (e) => (e.type === 'info' || e.type === 'error') && (e.step_name.includes('sandbox') || e.data.sandbox)
    )
  }, [progressEvents])

  const targetCodeSummary = useMemo(() => {
    const code = originalCode
    if (!code) return ''
    const lines = code.split('\n').slice(0, 10)
    return lines.join('\n')
  }, [originalCode])

  return {
    redScore,
    blueScore,
    currentRound,
    judgeScript,
    defenseData,
    allTestResults,
    attackScriptRounds,
    roundInfos,
    sandboxLogs,
    originalCode,
    targetCodeSummary,
    redStreamText,
    blueStreamText,
    judgeStreamText,
    fixedCodeVersions,
    latestFixedCode,
  }
}
