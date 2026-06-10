interface TestResultItem {
  id: number
  round: number
  name: string
  input: string
  expectedOutput: string
  actualOutput: string
  passed: boolean
  reason: string
}

export default function TestResultCard({ test }: { test: TestResultItem }): JSX.Element {
  return (
    <div
      className={`rounded p-2 text-[10px] border ${
        test.passed
          ? 'bg-green-900/10 border-green-500/20'
          : 'bg-red-900/10 border-red-500/20'
      }`}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span>{test.passed ? '✅' : '❌'}</span>
        <span className="font-medium text-foreground">{test.name}</span>
        <span className="text-muted-foreground/70 ml-auto">{'回合'} {test.round}</span>
      </div>
      {test.input && (
        <div className="text-muted-foreground">
          <span className="text-muted-foreground/70">{'输入:'} </span>
          <span className="font-mono">{test.input.slice(0, 80)}</span>
        </div>
      )}
      {test.expectedOutput && (
        <div className="text-muted-foreground">
          <span className="text-muted-foreground/70">{'期望:'} </span>
          <span className="font-mono">{test.expectedOutput.slice(0, 80)}</span>
        </div>
      )}
      {test.actualOutput && (
        <div className="text-muted-foreground">
          <span className="text-muted-foreground/70">{'实际:'} </span>
          <span className="font-mono">{test.actualOutput.slice(0, 80)}</span>
        </div>
      )}
      {test.reason && (
        <div className={`mt-1 ${test.passed ? 'text-green-400/70' : 'text-red-400/70'}`}>
          {test.reason}
        </div>
      )}
    </div>
  )
}
