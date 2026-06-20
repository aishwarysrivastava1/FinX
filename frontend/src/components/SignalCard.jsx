import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import { AlertTriangle, TrendingUp, TrendingDown, Minus, ExternalLink, BarChart3 } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

const SENTIMENT = {
  bullish: {
    label: 'Bullish',
    textCls: 'text-emerald-600 dark:text-emerald-400',
    bgCls:   'bg-emerald-50 border border-emerald-200 dark:bg-emerald-900/30 dark:border-emerald-700/50',
    icon: TrendingUp,
  },
  bearish: {
    label: 'Bearish',
    textCls: 'text-red-600 dark:text-red-400',
    bgCls:   'bg-red-50 border border-red-200 dark:bg-red-900/30 dark:border-red-700/50',
    icon: TrendingDown,
  },
  neutral: {
    label: 'Neutral',
    textCls: 'text-amber-600 dark:text-amber-400',
    bgCls:   'bg-amber-50 border border-amber-200 dark:bg-amber-900/30 dark:border-amber-700/50',
    icon: Minus,
  },
}

const fmt    = (v) => v != null ? `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—'
const fmtNum = (v) => v != null ? Number(v).toLocaleString('en-IN') : '—'
const fmtK   = (v) => v != null ? `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : '—'

function emaBgCls(signal) {
  if (!signal) return 'bg-gray-200 dark:bg-gray-700/60 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700/30'
  if (signal.includes('bullish')) return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/40'
  if (signal.includes('bearish')) return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800/40'
  return 'bg-gray-200 dark:bg-gray-700/60 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700/30'
}

function RangeBar({ low, high, current }) {
  if (low == null || high == null || current == null) return null
  const range = high - low
  if (range <= 0) return null
  const pos = Math.min(100, Math.max(0, ((current - low) / range) * 100))
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="text-[10px] text-gray-400 uppercase tracking-wider">52-Week Range</p>
        <p className="text-[10px] text-gray-400">{pos.toFixed(0)}% of range</p>
      </div>
      <div className="relative h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-visible">
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-red-400 via-amber-400 to-emerald-500 rounded-full"
          style={{ width: '100%', opacity: 0.35 }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-blue-600 rounded-full border-2 border-white dark:border-gray-900 shadow"
          style={{ left: `calc(${pos}% - 6px)` }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-gray-400">{fmtK(low)}</span>
        <span className="text-[10px] text-gray-400">{fmtK(high)}</span>
      </div>
    </div>
  )
}

function MiniChart({ prices = [], changePct = 0 }) {
  if (!prices || prices.length < 2) return null
  const isUp = (changePct ?? 0) >= 0
  const data = prices.map((v, i) => ({ i, v: Number(v) }))
  return (
    <ResponsiveContainer width="100%" height={60}>
      <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <Line type="monotone" dataKey="v" stroke={isUp ? '#10b981' : '#ef4444'} strokeWidth={1.5} dot={false} />
        <Tooltip
          content={({ payload }) =>
            payload?.[0] ? (
              <div className="bg-white dark:bg-gray-800 text-xs px-2 py-1 rounded border border-gray-200 dark:border-gray-700 shadow-lg">
                {fmt(payload[0].value)}
              </div>
            ) : null
          }
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

function StatBox({ label, value, cls = '' }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800/70 rounded-xl px-3 py-2.5 border border-gray-100 dark:border-gray-700/30">
      <p className="text-gray-500 dark:text-gray-500 text-[10px] uppercase tracking-wider font-semibold mb-1">{label}</p>
      <p className={`font-semibold text-sm ${cls || 'text-gray-900 dark:text-gray-100'}`}>{value}</p>
    </div>
  )
}

export default function SignalCard({ card }) {
  const [winRate, setWinRate] = useState(null)
  const [priceFlash, setPriceFlash] = useState(null)
  const prevPriceRef = useRef(null)

  useEffect(() => {
    if (!card?.symbol) return
    fetch(`${API_BASE}/analytics/success-rate/${card.symbol}?signal_type=${encodeURIComponent(card.ema_signal || 'EMA Crossover')}`)
      .then(r => r.json())
      .then(d => {
        if (d.win_rate != null) setWinRate({ pct: d.win_rate, n: d.occurrences ?? null })
      })
      .catch(() => {})
  }, [card?.symbol, card?.ema_signal])

  useEffect(() => {
    const curr = card?.current_price
    const prev = prevPriceRef.current
    prevPriceRef.current = curr
    if (prev == null || curr == null || prev === curr) return
    const dir = curr > prev ? 'up' : 'down'
    setPriceFlash(dir)
    const t = setTimeout(() => setPriceFlash(null), 600)
    return () => clearTimeout(t)
  }, [card?.current_price])

  if (!card) return null

  const s    = SENTIMENT[card.sentiment] || SENTIMENT.neutral
  const Icon = s.icon
  const isUp = (card.change_pct ?? 0) >= 0

  const rsiVal = card.rsi != null ? Number(card.rsi) : null
  const rsiBg  = rsiVal == null ? ''
    : rsiVal >= 70 ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800/40'
    : rsiVal <= 30 ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/40'
    : 'bg-gray-200 dark:bg-gray-700/60 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700/30'

  const sma200bg = (card.sma200 != null && card.current_price != null)
    ? (card.current_price >= card.sma200
        ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/40'
        : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800/40')
    : ''

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-5 space-y-5 relative shadow-sm dark:shadow-xl">

      {/* Win rate badge */}
      {winRate != null && (
        <div className="absolute top-4 right-4 bg-gradient-to-r from-indigo-600 to-purple-600
          text-white text-xs font-bold px-2.5 py-1 rounded-full shadow border border-purple-500/30 flex items-center gap-1">
          ★ {winRate.pct}% Win
          {winRate.n != null && winRate.n > 0 && (
            <span className="opacity-70 font-normal">· {winRate.n} signals</span>
          )}
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <h2 className="text-2xl font-extrabold text-gray-900 dark:text-white tracking-tight">{card.symbol}</h2>
            <span className="text-xs text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded-full border border-gray-200 dark:border-gray-700">NSE</span>
          </div>
          {card.current_price != null && (
            <div className="flex items-baseline gap-2 mt-1">
              <span className={`text-2xl font-bold tabular-nums transition-colors duration-300
                ${priceFlash === 'up' ? 'text-green-500 dark:text-green-400' :
                  priceFlash === 'down' ? 'text-red-500 dark:text-red-400' :
                  'text-gray-900 dark:text-gray-100'}`}>
                ₹{Number(card.current_price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </span>
              <span className={`text-sm font-semibold tabular-nums ${isUp ? 'text-green-600 dark:text-green-500' : 'text-red-600 dark:text-red-500'}`}>
                {isUp ? '▲ +' : '▼ '}{card.change_pct != null ? card.change_pct : '—'}%
              </span>
            </div>
          )}
        </div>
        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-semibold flex-shrink-0 ${s.bgCls} ${s.textCls}`}>
          <Icon className="w-3.5 h-3.5" />
          {s.label}
          {card.sentiment_score != null && (
            <span className="text-xs opacity-60">· {card.sentiment_score}</span>
          )}
        </div>
      </div>

      {/* Mini chart */}
      {card.price_30d?.length >= 2 && (
        <MiniChart prices={card.price_30d} changePct={card.change_pct} />
      )}

      {/* OHLC grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatBox label="Open"       value={fmt(card.open)} />
        <StatBox label="High"       value={fmt(card.high)}       cls="text-green-600 dark:text-green-500" />
        <StatBox label="Low"        value={fmt(card.low)}        cls="text-red-600 dark:text-red-500" />
        <StatBox label="Prev Close" value={fmt(card.prev_close)} />
      </div>
      {card.volume != null && (
        <div className="bg-gray-50 dark:bg-gray-800/70 border border-gray-100 dark:border-gray-700/30 rounded-xl px-4 py-2.5 flex items-center justify-between">
          <p className="text-gray-500 text-[10px] uppercase tracking-wider font-semibold">Volume</p>
          <p className="font-semibold text-sm text-gray-900 dark:text-gray-100">{fmtNum(card.volume)}</p>
        </div>
      )}

      {/* Technical Analysis */}
      <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700/20 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider font-semibold">Technical Analysis</p>
        </div>

        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{card.technical_snapshot || '—'}</p>

        {/* Indicator pills */}
        {(rsiVal != null || card.ema_signal || card.sma200 != null) && (
          <div className="flex flex-wrap gap-2 text-xs">
            {rsiVal != null && (
              <span className={`rounded-lg px-2.5 py-1 font-medium border ${rsiBg}`}>
                RSI {rsiVal}
                {card.rsi_zone && (
                  <span className="opacity-70 ml-1 capitalize">· {card.rsi_zone.replace(/_/g, ' ')}</span>
                )}
              </span>
            )}
            {card.ema_signal && (
              <span className={`rounded-lg px-2.5 py-1 font-medium border ${emaBgCls(card.ema_signal)}`}>
                EMA <span className="capitalize">{card.ema_signal.replace(/_/g, ' ')}</span>
              </span>
            )}
            {card.sma200 != null && card.current_price != null && (
              <span className={`rounded-lg px-2.5 py-1 font-medium border ${sma200bg}`}>
                {card.current_price >= card.sma200 ? '▲' : '▼'} SMA-200 {fmtK(card.sma200)}
              </span>
            )}
          </div>
        )}

        {/* EMA-20 / EMA-50 levels */}
        {(card.ema20 != null || card.ema50 != null) && (
          <div className="grid grid-cols-2 gap-2">
            {card.ema20 != null && (
              <div className="bg-white dark:bg-gray-900/60 rounded-lg px-3 py-2 border border-gray-100 dark:border-gray-700/30">
                <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-0.5">EMA-20</p>
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{fmt(card.ema20)}</p>
              </div>
            )}
            {card.ema50 != null && (
              <div className="bg-white dark:bg-gray-900/60 rounded-lg px-3 py-2 border border-gray-100 dark:border-gray-700/30">
                <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-0.5">EMA-50</p>
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{fmt(card.ema50)}</p>
              </div>
            )}
          </div>
        )}

        {/* 52-week range bar */}
        <RangeBar low={card.low_52w} high={card.high_52w} current={card.current_price} />
      </div>

      {/* News Impact — hidden when AI returned the fallback */}
      {card.news_impact_summary && card.news_impact_summary !== 'News data unavailable.' && (
        <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700/20 rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between mb-1">
            <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider font-semibold">News Impact</p>
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-24 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    (card.news_impact_score ?? 50) >= 60 ? 'bg-green-500' :
                    (card.news_impact_score ?? 50) >= 40 ? 'bg-amber-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${card.news_impact_score ?? 50}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 tabular-nums">{card.news_impact_score ?? '—'}/100</span>
            </div>
          </div>
          <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{card.news_impact_summary}</p>
        </div>
      )}

      {/* Risk Flags */}
      {card.risk_flags?.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider font-semibold">Risk Flags</p>
          <div className="space-y-1.5">
            {card.risk_flags.map((flag, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/20 rounded-lg px-3 py-2 border border-amber-100 dark:border-amber-900/20">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
                <span>{flag}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actionable Context */}
      {card.actionable_context && (
        <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800/30 rounded-xl p-4">
          <p className="text-sm text-blue-700 dark:text-blue-200 leading-relaxed">{card.actionable_context}</p>
        </div>
      )}

      {/* News Links */}
      {card.news?.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wider font-semibold mb-2">Recent News</p>
          <div className="divide-y divide-gray-100 dark:divide-gray-800/60">
            {card.news.map((n, i) => (
              <a
                key={i}
                href={n.url || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-2 py-2.5 text-xs text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 leading-relaxed transition-colors group"
              >
                <ExternalLink className="w-3 h-3 flex-shrink-0 mt-0.5" />
                <span>{n.headline}</span>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-xs text-gray-400 dark:text-gray-600 border-t border-gray-100 dark:border-gray-800 pt-3 leading-relaxed">
        {card.disclaimer || 'For educational purposes only. Not SEBI-registered investment advice.'}
      </p>
    </div>
  )
}
