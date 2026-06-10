import { useState, useEffect } from 'react'
import { useMotionValue, useSpring } from 'framer-motion'

export default function AnimatedNumber({ value, color }: { value: number; color: string }): JSX.Element {
  const motionVal = useMotionValue(0)
  const springVal = useSpring(motionVal, { stiffness: 80, damping: 20 })
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    motionVal.set(value)
  }, [value, motionVal])

  useEffect(() => {
    const unsub = springVal.on('change', (v) => setDisplay(Math.round(v)))
    return () => unsub()
  }, [springVal])

  return (
    <span className="tabular-nums" style={{ color }}>
      {display}
    </span>
  )
}
