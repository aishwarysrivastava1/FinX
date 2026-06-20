import { useState, useEffect, useRef } from 'react'
import { TrendingUp, TrendingDown, DollarSign, Gem, RefreshCw, AlertCircle, Zap } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

const fmt  = (v) => v != null ? `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—'
const sign = (v) => v > 0 ? '+' : ''

const SECTIONS = [
  {
    key:   'gainers',
    label: 'Top Gainers',
    icon:  TrendingUp,
    colorCls: 'text-green-600 dark:text-green-500',
    borderCls: 'border-green-200 dark:border-green-900/40',
    bgCls: 'bg-green-50 dark:bg-green-950/20',
    badgeCls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400',
  },
  {
    key:   'losers',
    label: 'Top Losers',
    icon:  TrendingDown,
    colorCls: 'text-red-600 dark:text-red-500',
    borderCls: 'border-red-200 dark:border-red-900/40',
    bgCls: 'bg-red-50 dark:bg-red-950/20',
    badgeCls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400',
  },
  {
    key:   'cheapest',
    label: 'Cheapest',
    icon:  DollarSign,
    colorCls: 'text-blue-600 dark:text-blue-400',
    borderCls: 'border-blue-200 dark:border-blue-900/40',
    bgCls: 'bg-blue-50 dark:bg-blue-950/20',
    badgeCls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400',
  },
  {
    key:   'expensive',
    label: 'Most Expensive',
    icon:  Gem,
    colorCls: 'text-purple-600 dark:text-purple-400',
    borderCls: 'border-purple-200 dark:border-purple-900/40',
    bgCls: 'bg-purple-50 dark:bg-purple-950/20',
    badgeCls: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-400',
  },
]

function MoverCard({ stock, badgeCls, onSelect }) {
  const isUp = (stock.change_pct ?? 0) >= 0
  const prevPriceRef = useRef(null)
  const [flash, setFlash] = useState(null) // 'up' | 'down' | null

  useEffect(() => {
    const curr = stock.price
    const prev = prevPriceRef.current
    prevPriceRef.current = curr
    if (prev == null || curr == null || prev === curr) return
    const dir = curr > prev ? 'up' : 'down'
    setFlash(dir)
    const t = setTimeout(() => setFlash(null), 700)
    return () => clearTimeout(t)
  }, [stock.price])

  return (
    <button
      onClick={() => onSelect?.(stock.symbol)}
      className={`flex-shrink-0 w-40 border border-gray-200 dark:border-gray-700
        rounded-xl p-3 text-left hover:border-blue-300 dark:hover:border-blue-600
        hover:shadow-md transition-all duration-300 cursor-pointer group
        ${flash === 'up' ? 'bg-green-50 dark:bg-green-950/40 border-green-300 dark:border-green-800' :
          flash === 'down' ? 'bg-red-50 dark:bg-red-950/40 border-red-300 dark:border-red-800' :
          'bg-white dark:bg-gray-800'}`}
    >
      <div className="flex items-start justify-between mb-1.5">
        <span className="text-xs font-bold text-gray-900 dark:text-white group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
          {stock.symbol}
        </span>
        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${badgeCls}`}>
          {sign(stock.change_pct)}{stock.change_pct != null ? stock.change_pct.toFixed(2) : '—'}%
        </span>
      </div>
      <p className="text-[10px] text-gray-400 truncate mb-2 leading-tight">{stock.name}</p>
      <p className={`text-sm font-bold tabular-nums transition-colors duration-300
        ${flash === 'up' ? 'text-green-600 dark:text-green-400' :
          flash === 'down' ? 'text-red-600 dark:text-red-400' :
          'text-gray-900 dark:text-gray-100'}`}>
        {fmt(stock.price)}
      </p>
    </button>
  )
}

function PlaceholderCard() {
  return (
    <div className="flex-shrink-0 w-40 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-3 animate-pulse">
      <div className="flex items-start justify-between mb-1.5">
        <div className="h-3 w-16 bg-gray-200 dark:bg-gray-700 rounded" />
        <div className="h-3 w-10 bg-gray-100 dark:bg-gray-600 rounded-full" />
      </div>
      <div className="h-2 w-24 bg-gray-100 dark:bg-gray-700 rounded mb-2" />
      <div className="h-4 w-14 bg-gray-200 dark:bg-gray-700 rounded" />
    </div>
  )
}

function SectionRow({ section, stocks, onSelect, marketOpen }) {
  const Icon = section.icon
  const list = stocks || []

  return (
    <div className={`rounded-2xl border ${section.borderCls} ${section.bgCls} p-4`}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className={`w-4 h-4 ${section.colorCls} flex-shrink-0`} />
        <h3 className={`text-sm font-bold ${section.colorCls}`}>{section.label}</h3>
        {marketOpen && list.length > 0 && (
          <span className="flex items-center gap-0.5 text-[9px] font-semibold text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 px-1.5 py-0.5 rounded-full border border-green-200 dark:border-green-800/40">
            <span className="w-1 h-1 rounded-full bg-green-500 animate-pulse inline-block" />
            LIVE
          </span>
        )}
        <span className="text-xs text-gray-400 ml-auto">{list.length} stocks</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1" style={{ scrollbarWidth: 'none' }}>
        {list.length > 0
          ? list.map(stock => (
              <MoverCard
                key={stock.symbol}
                stock={stock}
                badgeCls={section.badgeCls}
                onSelect={onSelect}
              />
            ))
          : Array.from({ length: 5 }).map((_, i) => <PlaceholderCard key={i} />)
        }
      </div>
    </div>
  )
}

export default function MarketMovers({ onSelectStock }) {
  const [data,      setData]    = useState(null)
  const [loading,   setLoading] = useState(true)
  const [error,     setError]   = useState(null)
  const [lastFetch, setLast]    = useState(null)
  const [marketOpen, setMarket] = useState(false)
  const pollRef     = useRef(null)

  const fetchMovers = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res  = await fetch(`${API_BASE}/market/movers`)
      const json = await res.json()
      if (json.success && json.data) {
        setData(json.data)
        setError(null)
        setLast(new Date())
      }
      // silent errors: keep existing data, don't show error banner
    } catch {
      // network blip — keep showing last known data silently
    } finally {
      setLoading(false)
    }
  }

  // Check market status once on mount
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res  = await fetch(`${API_BASE}/market/status`)
        const json = await res.json()
        setMarket(json.data?.is_open ?? false)
      } catch {
        // keep default (false = closed = 60s interval)
      }
    }
    checkStatus()
    const t = setInterval(checkStatus, 60_000)
    return () => clearInterval(t)
  }, [])

  // Market-aware polling: 5 s when open, 60 s when closed
  useEffect(() => {
    clearInterval(pollRef.current)
    fetchMovers()
    const interval = marketOpen ? 3_000 : 60_000
    pollRef.current = setInterval(() => fetchMovers(true), interval)
    return () => clearInterval(pollRef.current)
  }, [marketOpen])

  // Always render all 4 sections (no early "null" return when empty)
  if (loading && !data) {
    return (
      <div className="space-y-3">
        <div className="h-6 w-48 bg-gray-200 dark:bg-gray-800 rounded animate-pulse" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[1,2,3,4].map(i => (
            <div key={i} className="h-28 bg-gray-100 dark:bg-gray-800 rounded-2xl animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400 bg-gray-100 dark:bg-gray-800/50 rounded-xl p-3 border border-gray-200 dark:border-gray-700">
        <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0" />
        <span>{error}</span>
        <button onClick={() => fetchMovers()} className="ml-auto text-blue-600 dark:text-blue-400 hover:underline text-xs">Retry</button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-gray-900 dark:text-white">Market Movers</h2>
            {marketOpen && data && (
              <span className="flex items-center gap-1 text-[10px] font-semibold text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 px-1.5 py-0.5 rounded-full border border-green-200 dark:border-green-800/40">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse inline-block" />
                LIVE
              </span>
            )}
          </div>
          {lastFetch && data && (
            <p className="text-xs text-gray-400 mt-0.5">
              {data.total} stocks · {lastFetch.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </p>
          )}
        </div>
        <button
          onClick={() => fetchMovers(false)}
          disabled={loading}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {SECTIONS.map(section => (
          <SectionRow
            key={section.key}
            section={section}
            stocks={data?.[section.key] || []}
            onSelect={onSelectStock}
            marketOpen={marketOpen}
          />
        ))}
      </div>
    </div>
  )
}
