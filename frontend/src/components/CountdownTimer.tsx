import { useEffect, useState } from 'react'

export default function CountdownTimer({ expiresAt, onExpire }: { expiresAt: number; onExpire?: () => void }) {
  const [left, setLeft] = useState(Math.max(0, expiresAt - Math.floor(Date.now() / 1000)))
  useEffect(() => {
    const t = setInterval(() => {
      const l = Math.max(0, expiresAt - Math.floor(Date.now() / 1000))
      setLeft(l)
      if (l === 0) { clearInterval(t); onExpire?.() }
    }, 500)
    return () => clearInterval(t)
  }, [expiresAt, onExpire])
  const m = Math.floor(left / 60), s = left % 60
  return (
    <span role="timer" aria-live="off" className={`font-mono text-lg font-semibold ${left < 60 ? 'text-danger' : 'text-slate-900'}`}>
      {String(m).padStart(2, '0')}:{String(s).padStart(2, '0')}
    </span>
  )
}
