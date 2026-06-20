import { useState, useEffect, useRef } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, Minus, Activity, ChevronDown, ChevronUp } from 'lucide-react'

const RISK_STYLES = {
  high:   { border: 'border-l-red-500',     bg: 'bg-red-50/50 dark:bg-red-950/10',       badge: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300' },
  medium: { border: 'border-l-amber-500',   bg: 'bg-amber-50/50 dark:bg-amber-950/10',   badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300' },
  low:    { border: 'border-l-emerald-500', bg: 'bg-emerald-50/50 dark:bg-emerald-950/10', badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300' },
}

const SIG_ICON = {
  bullish: <TrendingUp   className="w-4 h-4 text-green-600 dark:text-green-500 flex-shrink-0" />,
  bearish: <TrendingDown className="w-4 h-4 text-red-600 dark:text-red-500 flex-shrink-0" />,
  neutral: <Minus        className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" />,
}

function emaPillCls(signal) {
  if (!signal) return 'bg-gray-100 dark:bg-gray-700/40 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700/30'
  if (signal.includes('bullish')) return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/40'
  if (signal.includes('bearish')) return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800/40'
  return 'bg-gray-100 dark:bg-gray-700/40 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700/30'
}

function TechPills({ s }) {
  const hasAny = s.rsi != null || s.ema_signal || s.ema20 != null || s.ema50 != null
    || s.sma200 != null || s.high_52w != null || s.low_52w != null
  if (!hasAny) return null

  const rsiVal = s.rsi != null ? Number(s.rsi) : null
  const rsiBg  = rsiVal == null ? ''
    : rsiVal >= 70 ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800/40'
    : rsiVal <= 30 ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/40'
    : 'bg-gray-100 dark:bg-gray-700/40 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700/30'

  const sma200Bg = (s.sma200 != null && s.price != null)
    ? (s.price >= s.sma200
        ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/40'
        : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800/40')
    : 'bg-gray-100 dark:bg-gray-700/40 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700/30'

  return (
    <div className="flex flex-wrap gap-1.5 text-xs pt-1">
      {rsiVal != null && (
        <span className={`rounded-md px-2 py-1 font-medium border ${rsiBg}`}>
          RSI {rsiVal}
          {s.rsi_zone && <span className="opacity-70 ml-1 capitalize">· {s.rsi_zone.replace(/_/g, ' ')}</span>}
        </span>
      )}
      {s.ema_signal && (
        <span className={`rounded-md px-2 py-1 font-medium border capitalize ${emaPillCls(s.ema_signal)}`}>
          EMA {s.ema_signal.replace(/_/g, ' ')}
        </span>
      )}
      {s.sma200 != null && (
        <span className={`rounded-md px-2 py-1 font-medium border ${sma200Bg}`}>
          {s.price != null ? (s.price >= s.sma200 ? '▲' : '▼') : ''} SMA-200 ₹{Number(s.sma200).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
      )}
      {s.ema20 != null && (
        <span className="rounded-md px-2 py-1 bg-gray-100 dark:bg-gray-700/40 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700/30">
          EMA-20 ₹{Number(s.ema20).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
      )}
      {s.ema50 != null && (
        <span className="rounded-md px-2 py-1 bg-gray-100 dark:bg-gray-700/40 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700/30">
          EMA-50 ₹{Number(s.ema50).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
      )}
      {s.high_52w != null && (
        <span className="rounded-md px-2 py-1 bg-gray-100 dark:bg-gray-700/40 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700/30">
          52W H ₹{Number(s.high_52w).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
      )}
      {s.low_52w != null && (
        <span className="rounded-md px-2 py-1 bg-gray-100 dark:bg-gray-700/40 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700/30">
          52W L ₹{Number(s.low_52w).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
      )}
    </div>
  )
}

function SignalItem({ s }) {
  const [open, setOpen] = useState(false)
  const [flash, setFlash] = useState(null)
  const prevPriceRef = useRef(null)
  const risk   = s.risk_level || 'medium'
  const styles = RISK_STYLES[risk] || RISK_STYLES.medium
  const isUp   = (s.percent_change ?? 0) >= 0
  const hasPx  = s.price != null
  const time   = (() => {
    try { return new Date(s.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) }
    catch { return '' }
  })()

  useEffect(() => {
    const curr = s.price
    const prev = prevPriceRef.current
    prevPriceRef.current = curr
    if (prev == null || curr == null || prev === curr) return
    const dir = curr > prev ? 'up' : 'down'
    setFlash(dir)
    const t = setTimeout(() => setFlash(null), 600)
    return () => clearTimeout(t)
  }, [s.price])

  return (
    <div
      onClick={() => setOpen(o => !o)}
      className={`border-l-4 rounded-r-xl p-4 cursor-pointer transition-all duration-150
        hover:shadow-sm ${styles.border} ${styles.bg}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5 flex-1 min-w-0">
          {SIG_ICON[s.signal_type] || SIG_ICON.neutral}
          <span className="font-bold text-gray-900 dark:text-white text-sm">{s.symbol}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize hidden sm:inline ${styles.badge}`}>
            {risk} risk
          </span>
          {s.ai_provider === 'rule_based' && (
            <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 hidden sm:inline">
              Rule-based AI
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {hasPx && (
            <div className="text-right">
              <p className={`text-sm font-bold tabular-nums transition-colors duration-300
                ${flash === 'up' ? 'text-green-500 dark:text-green-400' :
                  flash === 'down' ? 'text-red-500 dark:text-red-400' :
                  'text-gray-900 dark:text-gray-100'}`}>
                ₹{Number(s.price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </p>
              <p className={`text-xs font-semibold tabular-nums ${isUp ? 'text-green-600 dark:text-green-500' : 'text-red-600 dark:text-red-500'}`}>
                {isUp ? '+' : ''}{s.percent_change != null ? Number(s.percent_change).toFixed(2) : '—'}%
              </p>
            </div>
          )}
          <div className="text-right hidden sm:block">
            <p className="text-xs text-gray-500 capitalize">{s.signal_type || 'neutral'}</p>
            <p className="text-xs text-gray-400 dark:text-gray-600">{time}</p>
          </div>
          {open
            ? <ChevronUp   className="w-4 h-4 text-gray-400 flex-shrink-0" />
            : <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
          }
        </div>
      </div>

      {open && (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700/40 space-y-2">
          {s.explanation && (
            <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{s.explanation}</p>
          )}

          <TechPills s={s} />

          {s.key_observation && (
            <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-100 dark:border-blue-800/30 rounded-lg px-3 py-2">
              <p className="text-xs text-blue-700 dark:text-blue-300 leading-relaxed">
                <span className="font-semibold">Key Observation: </span>{s.key_observation}
              </p>
            </div>
          )}
          {s.disclaimer && (
            <p className="text-xs text-gray-400 dark:text-gray-600 leading-relaxed">{s.disclaimer}</p>
          )}
        </div>
      )}
    </div>
  )
}

function SkeletonItem() {
  return (
    <div className="border-l-4 border-l-gray-200 dark:border-l-gray-700 rounded-r-xl p-4 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-4 h-4 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="w-16 h-4 bg-gray-200 dark:bg-gray-700 rounded" />
          <div className="w-20 h-4 bg-gray-100 dark:bg-gray-800 rounded-full hidden sm:block" />
        </div>
        <div className="w-16 h-8 bg-gray-200 dark:bg-gray-700 rounded" />
      </div>
    </div>
  )
}

export default function SignalFeed({ signals = [], loading, onRefresh, lastUpdated, marketOpen }) {
  const [filter, setFilter] = useState('all')
  const FILTERS = ['all', 'high', 'medium', 'low']
  const shown = filter === 'all' ? signals : signals.filter(s => s.risk_level === filter)
  const count = (r) => signals.filter(s => s.risk_level === r).length

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">Opportunity Radar</h2>
            {marketOpen && signals.length > 0 && (
              <span className="flex items-center gap-1 text-[10px] font-semibold text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 px-1.5 py-0.5 rounded-full border border-green-200 dark:border-green-800/40">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse inline-block" />
                LIVE
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            {lastUpdated
              ? `Updated ${new Date(lastUpdated).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
              : 'NSE bulk & block deal signals'
            }
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-500
            disabled:bg-gray-200 dark:disabled:bg-gray-700 disabled:cursor-not-allowed
            rounded-lg text-sm font-medium text-white disabled:text-gray-500
            transition-colors shadow-sm"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Scanning…' : 'Scan NSE'}
        </button>
      </div>

      {/* Filter pills */}
      <div className="flex gap-2 flex-wrap">
        {FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition-colors
              ${filter === f
                ? 'bg-blue-600 text-white shadow-sm'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
          >
            {f === 'all' ? `All (${signals.length})` : `${f} (${count(f)})`}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="space-y-2">
        {loading && !signals.length && Array.from({ length: 3 }).map((_, i) => <SkeletonItem key={i} />)}
        {!loading && !shown.length && (
          <div className="text-center py-20 text-gray-400 dark:text-gray-600">
            <Activity className="w-10 h-10 mx-auto mb-3 opacity-20" />
            <p className="text-sm">
              {signals.length
                ? `No ${filter} risk signals found`
                : 'No signals yet — click Scan NSE to fetch bulk deals'
              }
            </p>
          </div>
        )}
        {shown.map(s => <SignalItem key={s.id} s={s} />)}
      </div>
    </div>
  )
}
