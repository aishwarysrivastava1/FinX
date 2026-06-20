import { useEffect, useState } from 'react'
import { pingHealth } from '../api'

export default function WarmupBanner() {
  const [warmup, setWarmup] = useState({
    warming_up: false,
    warmup_stage: '',
    warmup_progress: 0,
  })

  useEffect(() => {
    let mounted = true

    async function tick() {
      try {
        const res = await pingHealth()
        if (!mounted) return
        setWarmup({
          warming_up: !!res?.warming_up,
          warmup_stage: res?.warmup_stage || '',
          warmup_progress: Number(res?.warmup_progress || 0),
        })
      } catch {
        // Non-critical UX: keep banner hidden on transient health failures.
      }
    }

    tick()
    const id = setInterval(tick, 3000)
    return () => {
      mounted = false
      clearInterval(id)
    }
  }, [])

  if (!warmup.warming_up) return null

  return (
    <div className="mb-3">
      <div className="rounded-lg border border-amber-200 bg-amber-50 dark:bg-amber-950/40 dark:border-amber-900 px-4 py-3 text-sm">
        <div className="font-semibold text-amber-900 dark:text-amber-100">
          FIN-X is warming up...
        </div>
        <div className="text-amber-800 dark:text-amber-200">
          {warmup.warmup_stage ? warmup.warmup_stage : 'initializing'} · {warmup.warmup_progress}%
        </div>
      </div>
    </div>
  )
}

