import { useState, useEffect, useCallback } from 'react'
import SignalFeed from '../components/SignalFeed'
import ClusterRadar from '../components/ClusterRadar'
import MarketMovers from '../components/MarketMovers'
import { fetchSignals, refreshRadar, fetchMarketStatus } from '../api'

const REFRESH_MS = 5_000    // refresh signal prices every 5 s (matches backend cache TTL)

export default function RadarPage({ onSelectStock }) {
  const [signals,     setSignals]  = useState([])
  const [loading,     setLoading]  = useState(false)
  const [lastUpdated, setLast]     = useState(null)
  const [marketOpen,  setMarket]   = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await fetchSignals({ limit: 30 })
      const fresh = data.signals || []
      if (fresh.length > 0) {
        setSignals(fresh)
        setLast(new Date().toISOString())
      }
    } catch (e) {
      console.error('[Radar]', e.message)
      // keep existing signals — never go blank on error
    }
  }, [])

  const handleRefresh = async () => {
    setLoading(true)
    try { await refreshRadar(); await load() }
    catch (e) { console.error('[Refresh]', e.message) }
    finally { setLoading(false) }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, REFRESH_MS)
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    const check = async () => {
      try {
        const data = await fetchMarketStatus()
        setMarket(data.is_open ?? false)
      } catch { /* keep last value */ }
    }
    check()
    const t = setInterval(check, 30_000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="space-y-6">
      {/* Market Movers — gainers, losers, cheapest, expensive */}
      <MarketMovers onSelectStock={onSelectStock} />

      {/* Institutional cluster intelligence */}
      <ClusterRadar />

      {/* AI-explained bulk deal signals */}
      <SignalFeed
        signals={signals}
        loading={loading}
        onRefresh={handleRefresh}
        lastUpdated={lastUpdated}
        marketOpen={marketOpen}
      />
    </div>
  )
}
