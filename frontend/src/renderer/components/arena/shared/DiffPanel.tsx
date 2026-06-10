import { useState, useEffect, useMemo } from 'react'

interface DiffLine {
  type: 'same' | 'added' | 'removed' | 'changed'
  original: string
  fixed: string
}

interface CodeVersion {
  round: number
  code: string
  timestamp: number
}

function computeDiff(original: string, fixed: string): DiffLine[] {
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

export default function DiffPanel({
  versions,
  originalCode,
}: {
  versions: CodeVersion[]
  originalCode: string
}): JSX.Element {
  const allVersions = useMemo(() => {
    const list: CodeVersion[] = []
    if (originalCode) {
      list.push({ round: 0, code: originalCode, timestamp: 0 })
    }
    versions.forEach((v) => list.push(v))
    return list
  }, [versions, originalCode])

  const [leftIdx, setLeftIdx] = useState(0)
  const [rightIdx, setRightIdx] = useState(0)

  useEffect(() => {
    if (allVersions.length > 0) {
      setRightIdx(allVersions.length - 1)
      setLeftIdx(0)
    }
  }, [allVersions.length])

  const leftCode = allVersions[leftIdx]?.code ?? ''
  const rightCode = allVersions[rightIdx]?.code ?? ''

  const diffLines = useMemo(() => computeDiff(leftCode, rightCode), [leftCode, rightCode])

  const versionLabel = (v: CodeVersion): string => {
    if (v.round === 0) return '原始代码'
    return `第${v.round}回合修复`
  }

  if (allVersions.length === 0) {
    return (
      <div className="rounded-lg border border-border overflow-hidden">
        <div className="px-3 py-2 bg-card">
          <span className="text-accent-cyan text-sm font-medium">{'🔍'} 代码 Diff</span>
        </div>
        <div className="text-xs text-muted-foreground text-center py-8">{'等待目标代码...'}</div>
      </div>
    )
  }

  if (allVersions.length === 1) {
    return (
      <div className="rounded-lg border border-border overflow-hidden">
        <div className="px-3 py-2 bg-card flex items-center gap-3 flex-wrap">
          <span className="text-accent-cyan text-sm font-medium">{'🔍'} 代码 Diff</span>
        </div>
        <div className="bg-muted">
          <div className="sticky top-0 px-2 py-1 bg-card text-xs text-foreground font-medium border-b border-border">
            {'原始代码'} <span className="text-muted-foreground ml-1">{'暂无修复版本，展示原始代码'}</span>
          </div>
          {originalCode.split('\n').map((line, i) => (
            <div key={i} className="px-2 py-0.5 font-mono text-xs leading-relaxed text-muted-foreground">
              <span className="inline-block w-6 text-muted-foreground/70 select-none text-right mr-2">
                {i + 1}
              </span>
              {line || '\u00A0'}
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="px-3 py-2 bg-card flex items-center gap-3 flex-wrap">
        <span className="text-accent-cyan text-sm font-medium">{'🔍'} 代码 Diff</span>
        <div className="flex items-center gap-2 text-xs">
          <select
            value={leftIdx}
            onChange={(e) => setLeftIdx(Number(e.target.value))}
            className="bg-muted border border-border rounded px-2 py-1 text-foreground focus:outline-none"
          >
            {allVersions.map((v, i) => (
              <option key={i} value={i}>
                {versionLabel(v)}
              </option>
            ))}
          </select>
          <span className="text-muted-foreground">vs</span>
          <select
            value={rightIdx}
            onChange={(e) => setRightIdx(Number(e.target.value))}
            className="bg-muted border border-border rounded px-2 py-1 text-foreground focus:outline-none"
          >
            {allVersions.map((v, i) => (
              <option key={i} value={i}>
                {versionLabel(v)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 divide-x divide-border max-h-80 overflow-auto">
        <div className="bg-muted">
          <div className="sticky top-0 px-2 py-1 bg-card text-xs text-red-400 font-medium border-b border-border">
            {versionLabel(allVersions[leftIdx] ?? { round: 0, code: '', timestamp: 0 })}
          </div>
          {diffLines.map((line, i) => (
            <div
              key={i}
              className={`px-2 py-0.5 font-mono text-xs leading-relaxed ${
                line.type === 'removed'
                  ? 'bg-red-900/30 text-red-300'
                  : line.type === 'changed'
                    ? 'bg-orange-900/30 text-orange-300'
                    : 'text-muted-foreground'
              }`}
            >
              <span className="inline-block w-6 text-muted-foreground/70 select-none text-right mr-2">
                {i + 1}
              </span>
              {line.original || '\u00A0'}
            </div>
          ))}
        </div>
        <div className="bg-muted">
          <div className="sticky top-0 px-2 py-1 bg-card text-xs text-green-400 font-medium border-b border-border">
            {versionLabel(allVersions[rightIdx] ?? { round: 0, code: '', timestamp: 0 })}
          </div>
          {diffLines.map((line, i) => (
            <div
              key={i}
              className={`px-2 py-0.5 font-mono text-xs leading-relaxed ${
                line.type === 'added'
                  ? 'bg-green-900/30 text-green-300'
                  : line.type === 'changed'
                    ? 'bg-orange-900/30 text-orange-300'
                    : 'text-muted-foreground'
              }`}
            >
              <span className="inline-block w-6 text-muted-foreground/70 select-none text-right mr-2">
                {i + 1}
              </span>
              {line.fixed || '\u00A0'}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
