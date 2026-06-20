import { useState, useEffect, useRef, useCallback } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import SignalCard from '../components/SignalCard'
import SearchBar from '../components/SearchBar'
import { fetchSignalCard, fetchQuickPrice, fetchMarketStatus, fetchMarketChart, getMarketWsUrl } from '../api'
import { RefreshCw, Wifi, Activity, Loader2 } from 'lucide-react'

const POPULAR = [
  'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK',
  'WIPRO', 'BAJFINANCE', 'SUNPHARMA', 'ITC',
]

const TREND_KEYS  = { '1D': '1d', '1W': '1w', '1M': '1m', '1Y': '1y', '5Y': '5y', 'ALL': 'max' }
const TREND_LABEL = { '1D': 'Intraday', '1W': '5 Days', '1M': '30 Days', '1Y': '1 Year', '5Y': '5 Years', 'ALL': 'All Time' }

// ── Module-level card cache (survives re-renders, resets on hard reload) ──
// Keyed by symbol. TTL 5 min — ensures returning to a stock is instant.
const _cardCache = new Map()  // symbol → { card, ts }
const CARD_CACHE_TTL = 5 * 60 * 1000

function _getCached(sym) {
  const e = _cardCache.get(sym)
  if (!e) return null
  if (Date.now() - e.ts > CARD_CACHE_TTL) { _cardCache.delete(sym); return null }
  return e.card
}

// ── Trend Chart ──────────────────────────────────────────────
function TrendChart({ symbol, trends, liveIntraday, marketOpen }) {
  const [tab, setTab] = useState('1D')
  const [fetched, setFetched] = useState({})
  const [loadingTab, setLoadingTab] = useState(false)
  if (!trends) return null

  const key = TREND_KEYS[tab]
  // For 1D: NEVER use trends['1d'] — card prefetch stores daily (not intraday) data there.
  // Use WebSocket live intraday first, then API-fetched intraday, then empty (triggers fetch).
  const liveOrStored =
    tab === '1D'
      ? (liveIntraday?.length >= 2 ? liveIntraday : (fetched['1d'] || []))
      : (fetched[key] || trends[key] || [])

  const raw = liveOrStored

  const data    = raw.map(d => ({ ...d, price: Number(d.price) }))
  const hasData = data.length >= 2
  const first   = hasData ? data[0].price : 0
  const last    = hasData ? data[data.length - 1].price : 0
  const isUp    = last >= first
  const pctMove = first ? (((last - first) / first) * 100).toFixed(2) : null
  const color   = isUp ? '#10b981' : '#ef4444'

  const fmtTick = (v) => {
    if (!v) return ''
    const s = String(v)
    const d = new Date(s)
    if (isNaN(d)) return s.slice(-5)
    if (s.includes('T') || (s.includes(':') && !s.includes('-'))) {
      return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' })
    }
    return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
  }

  const fmtLabel = (v) => {
    if (!v) return ''
    const s = String(v)
    const d = new Date(s)
    if (isNaN(d)) return s
    if (s.includes('T') || (s.includes(':') && !s.includes('-'))) {
      return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }) + ' IST'
    }
    return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  useEffect(() => {
    let cancelled = false
    const loadTab = async () => {
      if (!symbol) return
      if (tab === '1D') {
        // Always fetch fresh intraday — don't rely on trends['1d'] which may be daily data
        if ((fetched['1d'] || []).length >= 2) return  // already fetched this session
        // fall through to fetch proper 5-min intraday
      } else {
        const current = fetched[key] || trends[key] || []
        if (current.length >= 2) return
      }
      try {
        setLoadingTab(true)
        const data = await fetchMarketChart(symbol, key)
        if (cancelled) return
        const points = data?.points || []
        setFetched(prev => ({ ...prev, [key]: points }))
      } catch {
        // keep existing data if fetch fails
      } finally {
        if (!cancelled) setLoadingTab(false)
      }
    }
    loadTab()
    return () => { cancelled = true }
  }, [symbol, key]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-4 shadow-sm dark:shadow-lg">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">Price Trend</p>
            {tab === '1D' && marketOpen && (
              <span className="flex items-center gap-1 text-[10px] font-semibold text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 px-1.5 py-0.5 rounded-full border border-green-200 dark:border-green-800/50">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse inline-block" />
                LIVE
              </span>
            )}
            {loadingTab && (
              <span className="text-[10px] text-blue-500">loading...</span>
            )}
          </div>
          {hasData && pctMove !== null && (
            <p className={`text-xs font-semibold mt-0.5 ${isUp ? 'text-green-600 dark:text-green-500' : 'text-red-600 dark:text-red-500'}`}>
              {isUp ? '▲ +' : '▼ '}{pctMove}% · {TREND_LABEL[tab]}
            </p>
          )}
        </div>
        <div className="flex gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5 border border-gray-200 dark:border-gray-700">
          {['1D', '1W', '1M', '1Y', '5Y', 'ALL'].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all duration-150
                ${tab === t
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {hasData ? (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
            <XAxis
              dataKey="time"
              tick={{ fill: '#9ca3af', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
              tickFormatter={fmtTick}
            />
            <YAxis hide domain={['auto', 'auto']} />
            <Tooltip
              content={({ payload, label }) =>
                payload?.[0] ? (
                  <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 shadow-xl text-xs">
                    <p className="text-gray-500 mb-0.5">{fmtLabel(label)}</p>
                    <p className="text-gray-900 dark:text-white font-bold">
                      ₹{Number(payload[0].value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                    </p>
                  </div>
                ) : null
              }
            />
            <Line
              type="monotone"
              dataKey="price"
              stroke={color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: color, strokeWidth: 0 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="h-[180px] flex items-center justify-center text-gray-400 text-sm">
          No {tab} data available
        </div>
      )}
    </div>
  )
}

// ── Quick Price View (shown instantly while full card loads) ──
// Displays price + OHLCV from the fast /market/price endpoint.
// Replaced by the full SignalCard once the AI analysis arrives.
function QuickPriceView({ symbol, liveData }) {
  const isUp = (liveData?.change_pct ?? 0) >= 0
  const fmt  = (v) => v != null
    ? `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
    : '—'
  const prevPriceRef = useRef(null)
  const [flash, setFlash] = useState(null)

  useEffect(() => {
    const curr = liveData?.price
    const prev = prevPriceRef.current
    prevPriceRef.current = curr
    if (prev == null || curr == null || prev === curr) return
    const dir = curr > prev ? 'up' : 'down'
    setFlash(dir)
    const t = setTimeout(() => setFlash(null), 600)
    return () => clearTimeout(t)
  }, [liveData?.price])

  return (
    <div className="space-y-4">
      {/* Price tile */}
      <div className={`border rounded-2xl p-5 shadow-sm transition-colors duration-300
        ${flash === 'up' ? 'bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800/50' :
          flash === 'down' ? 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800/50' :
          'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800'}`}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">NSE</p>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{symbol}</h2>
            <div className="flex items-baseline gap-2 mt-1">
              <span className={`text-3xl font-bold tabular-nums transition-colors duration-300
                ${flash === 'up' ? 'text-green-600 dark:text-green-400' :
                  flash === 'down' ? 'text-red-600 dark:text-red-400' :
                  'text-gray-900 dark:text-white'}`}>
                {fmt(liveData?.price)}
              </span>
              <span className={`text-base font-semibold tabular-nums ${isUp ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                {isUp ? '+' : ''}{liveData?.change_pct != null ? liveData.change_pct.toFixed(2) : '—'}%
              </span>
            </div>
          </div>
          <span className="flex items-center gap-1.5 text-[10px] text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800/40 px-2 py-1 rounded-full">
            <Loader2 className="w-3 h-3 animate-spin" />
            Loading analysis
          </span>
        </div>

        {/* OHLCV grid */}
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'Open',       value: fmt(liveData?.open) },
            { label: 'High',       value: fmt(liveData?.high) },
            { label: 'Low',        value: fmt(liveData?.low) },
            { label: 'Prev Close', value: fmt(liveData?.prev_close) },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-50 dark:bg-gray-800 rounded-xl p-2.5 text-center">
              <p className="text-[10px] text-gray-400 mb-0.5">{label}</p>
              <p className="text-xs font-bold text-gray-900 dark:text-white tabular-nums">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Analysis loading skeleton */}
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-5 space-y-3 animate-pulse">
        <div className="h-5 bg-gray-100 dark:bg-gray-800 rounded w-40" />
        <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-full" />
        <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-5/6" />
        <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-4/6" />
        <div className="grid grid-cols-3 gap-2 pt-1">
          {[1,2,3].map(i => <div key={i} className="h-10 bg-gray-100 dark:bg-gray-800 rounded-xl" />)}
        </div>
      </div>
    </div>
  )
}

// ── Full loading skeleton (only while waiting for quick price) ─
function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-4 h-56" />
      <div className="bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-5 space-y-4">
        <div className="h-7 bg-gray-200 dark:bg-gray-800 rounded w-36" />
        <div className="h-5 bg-gray-200 dark:bg-gray-800 rounded w-52" />
        <div className="grid grid-cols-4 gap-2">
          {[1, 2, 3, 4].map(i => <div key={i} className="h-12 bg-gray-200 dark:bg-gray-800 rounded-xl" />)}
        </div>
        <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-full" />
        <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-4/5" />
        <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded w-3/5" />
      </div>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────
export default function CardPage({ initialSym = '' }) {
  const [sym,        setSym]   = useState('')
  const [card,       setCard]  = useState(null)
  const [loading,    setLoad]  = useState(false)   // full card is loading
  const [error,      setError] = useState(null)

  // Live overlay — price + intraday updated every 4 s
  const [liveData,   setLive]   = useState(null)
  const [marketOpen, setMarket] = useState(false)
  const [timeIST,    setTime]   = useState('')

  const cardPollRef  = useRef(null)
  const wsRef        = useRef(null)
  const marketRef    = useRef(null)
  // Tracks which symbol is currently "wanted" — stale responses are discarded
  const activeSymRef = useRef('')

  // ── Full card load (cache-first, never blanks UI) ─────────
  const loadCard = useCallback(async (ticker, forceRefresh = false) => {
    if (!ticker) return

    // Serve from module-level cache unless force-refreshing
    if (!forceRefresh) {
      const cached = _getCached(ticker)
      if (cached) {
        if (activeSymRef.current === ticker) {
          setCard(cached)
          setLoad(false)
          setError(null)
        }
        return
      }
    }

    setLoad(true)
    try {
      const data    = await fetchSignalCard(ticker, forceRefresh)
      const newCard = data.card
      _cardCache.set(ticker, { card: newCard, ts: Date.now() })
      // Discard if user has since selected a different symbol
      if (activeSymRef.current !== ticker) return
      setCard(newCard)
      setError(null)
    } catch (e) {
      if (activeSymRef.current !== ticker) return
      setError(`Could not load ${ticker}: ${e.message}`)
    } finally {
      if (activeSymRef.current === ticker) setLoad(false)
    }
  }, [])

  // ── Quick price fetch (fast path — no AI, < 200 ms from cache) ─
  const fetchQuick = useCallback(async (ticker) => {
    if (!ticker) return
    try {
      const data = await fetchQuickPrice(ticker)
      if (activeSymRef.current !== ticker) return
      setLive(data)
      setMarket(data.market_open ?? false)
      setTime(data.time_ist ?? '')
    } catch {
      // silent — live poll will fill this shortly
    }
  }, [])

  const stopWs = useCallback(() => {
    try {
      if (wsRef.current) {
        wsRef.current.onopen = null
        wsRef.current.onmessage = null
        wsRef.current.onerror = null
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    } catch {
      // ignore
    } finally {
      wsRef.current = null
    }
  }, [])

  const startWs = useCallback((ticker) => {
    if (!ticker) return
    stopWs()
    try {
      const ws = new window.WebSocket(getMarketWsUrl(ticker))
      wsRef.current = ws
      ws.onmessage = (evt) => {
        try {
          const payload = JSON.parse(evt.data || '{}')
          if (!payload?.success || !payload?.data) return
          if (activeSymRef.current !== ticker) return
          const d = payload.data
          setLive(d)
          setMarket(d.market_open ?? false)
          setTime(d.time_ist ?? '')
        } catch {
          // ignore malformed frame
        }
      }
    } catch {
      // silent: quick price + card data still render
    }
  }, [stopWs])

  useEffect(() => () => stopWs(), [stopWs])

  // ── Market status poll (60 s) ─────────────────────────────
  const checkMarket = useCallback(async () => {
    try {
      const data = await fetchMarketStatus()
      setMarket(data.is_open ?? false)
      setTime(data.time_ist ?? '')
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    checkMarket()
    marketRef.current = setInterval(checkMarket, 60_000)
    return () => clearInterval(marketRef.current)
  }, [checkMarket])

  // Auto-load when navigated from MarketMovers or external source
  useEffect(() => {
    if (initialSym) {
      clearInterval(cardPollRef.current)
      stopWs()
      activeSymRef.current = initialSym
      setSym(initialSym)
      setLive(null)
      setError(null)

      const cached = _getCached(initialSym)
      if (cached) {
        setCard(cached); setLoad(false)
      } else {
        setCard(null); setLoad(true)
        fetchQuick(initialSym)   // fast path: price tile in < 200 ms
      }
      loadCard(initialSym, false)
      startWs(initialSym)
    }
  }, [initialSym, loadCard, fetchQuick, startWs, stopWs])

  // Full-card silent refresh every 5 min (cache-served — no force refresh)
  useEffect(() => {
    if (!sym) return
    clearInterval(cardPollRef.current)
    cardPollRef.current = setInterval(async () => {
      try {
        const data = await fetchSignalCard(sym, false)
        if (activeSymRef.current !== sym) return
        const newCard = data.card
        _cardCache.set(sym, { card: newCard, ts: Date.now() })
        setCard(newCard)
      } catch { /* silent — keep last card */ }
    }, 5 * 60_000)
    return () => clearInterval(cardPollRef.current)
  }, [sym])

  // ── Stock selection ───────────────────────────────────────
  const handleSelect = (ticker) => {
    if (!ticker) return
    clearInterval(cardPollRef.current)
    stopWs()

    activeSymRef.current = ticker
    setSym(ticker)
    setLive(null)
    setError(null)

    const cached = _getCached(ticker)
    if (cached) {
      // Instant: serve from module-level cache
      setCard(cached)
      setLoad(false)
    } else {
      // Two-phase: show price tile ASAP, then load full card
      setCard(null)
      setLoad(true)
      fetchQuick(ticker)   // fast path — price shows in < 200 ms
    }
    loadCard(ticker, false)
    startWs(ticker)
  }

  // Merge live overlay into display card (price + OHLCV only)
  const displayCard = card ? {
    ...card,
    current_price: liveData?.price      ?? card.current_price,
    change_pct:    liveData?.change_pct  ?? card.change_pct,
    change:        liveData?.change      ?? card.change,
    open:          liveData?.open        ?? card.open,
    high:          liveData?.high        ?? card.high,
    low:           liveData?.low         ?? card.low,
    volume:        liveData?.volume      ?? card.volume,
  } : null

  return (
    <div className="space-y-5">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">NSE Signal Card</h2>
          <p className="text-sm text-gray-500 mt-0.5">AI-powered stock analysis · Live NSE data</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1.5 text-[10px] font-semibold px-2 py-1 rounded-full border
            ${marketOpen
              ? 'text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800/50'
              : 'text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
            }`}
          >
            <Activity className="w-2.5 h-2.5" />
            {marketOpen ? `OPEN · ${timeIST} IST` : timeIST ? `CLOSED · ${timeIST} IST` : 'Checking…'}
          </span>

          {card && !loading && liveData && (
            <span className="flex items-center gap-1 text-xs text-gray-400">
              <Wifi className="w-3 h-3 animate-pulse text-green-500" />
              Live
            </span>
          )}
          {(card || liveData) && !loading && sym && (
            <button
              onClick={() => {
                activeSymRef.current = sym
                _cardCache.delete(sym)   // bust frontend cache → forces backend fetch
                loadCard(sym, false)     // use backend L1 cache if fresh, else regenerate
                startWs(sym)            // reconnect WebSocket for immediate live data
              }}
              title="Force refresh"
              className="p-2 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Smart search */}
      <SearchBar onSelect={handleSelect} />

      {/* Popular stocks */}
      <div className="flex flex-wrap gap-2">
        {POPULAR.filter(Boolean).map(s => (
          <button
            key={s}
            onClick={() => handleSelect(s)}
            className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-all duration-150
              ${sym === s
                ? 'bg-blue-600 border-blue-500 text-white shadow-sm'
                : 'bg-gray-100 dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-blue-400 dark:hover:border-blue-600 hover:text-gray-900 dark:hover:text-white'
              }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && !loading && (
        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/50 rounded-xl p-4 flex items-center justify-between">
          <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
          <button
            onClick={() => loadCard(sym, false)}
            className="text-xs text-red-600 dark:text-red-400 hover:underline ml-3 flex-shrink-0"
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && !card && !liveData && !sym && (
        <div className="text-center py-20 text-gray-400">
          <p className="text-sm">Search for a stock or click a popular ticker above</p>
        </div>
      )}

      {/*
        Rendering priority (in order):
        1. Full card (AI analysis complete) — richest view
        2. QuickPriceView (live price arrived, AI still loading)
        3. Full skeleton (nothing yet — only briefly, < 200 ms on warm cache)
      */}

      {/* ── Full card ── */}
      {displayCard && (
        <div className="space-y-4">
          {/* Subtle refresh indicator on top of existing card */}
          {loading && (
            <div className="flex items-center gap-2 text-xs text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800/40 rounded-lg px-3 py-2">
              <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
              Updating analysis…
            </div>
          )}
          <TrendChart
            symbol={sym}
            trends={card.trends}
            liveIntraday={liveData?.intraday}
            marketOpen={marketOpen}
          />
          <SignalCard card={displayCard} />
        </div>
      )}

      {/* ── Quick price view (price arrived, AI pending) ── */}
      {!displayCard && loading && liveData && (
        <QuickPriceView symbol={sym} liveData={liveData} />
      )}

      {/* ── Full skeleton (nothing arrived yet) ── */}
      {!displayCard && loading && !liveData && <Skeleton />}
    </div>
  )
}
