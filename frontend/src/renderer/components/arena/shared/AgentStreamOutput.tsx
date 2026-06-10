import { useState, useEffect, useRef } from 'react'

export default function AgentStreamOutput({
  fullText,
  isActive,
}: {
  fullText: string
  isActive: boolean
}): JSX.Element {
  const [displayLen, setDisplayLen] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    setDisplayLen(0)
  }, [fullText])

  useEffect(() => {
    if (!isActive) return

    intervalRef.current = setInterval(() => {
      setDisplayLen((prev) => {
        if (prev >= fullText.length) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
          }
          return prev
        }
        return prev + 1
      })
    }, 30)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [fullText, isActive])

  const displayed = fullText.slice(0, displayLen)
  const showCursor = isActive && displayLen < fullText.length

  return (
    <div className="font-mono text-xs whitespace-pre-wrap break-all text-foreground leading-relaxed">
      <span>{displayed}</span>
      {showCursor && (
        <span className="inline-block w-1.5 h-3.5 bg-accent-cyan animate-pulse align-middle">
          {'▌'}
        </span>
      )}
    </div>
  )
}
