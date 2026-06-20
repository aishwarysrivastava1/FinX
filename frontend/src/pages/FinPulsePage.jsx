import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, Newspaper, RefreshCw } from 'lucide-react'
import { fetchFinPulse } from '../api'

const SENTIMENT_STYLES = {
  positive: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
  negative: 'bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800',
  neutral: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700',
}

export default function FinPulsePage({ onSelectStock }) {
  const [items, setItems] = useState([])
  const [cachedAt, setCachedAt] = useState(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)

  const load = useCallback(async (force) => {
    setErr(null)
    setLoading(true)
    try {
      const data = await fetchFinPulse(force)
      setItems(data.items || [])
      setCachedAt(data.cached_at || null)
    } catch (e) {
      setErr(e.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(false)
  }, [load])

  const goToStock = (sym) => {
    if (sym && onSelectStock) onSelectStock(sym)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Newspaper className="w-6 h-6 text-blue-600 dark:text-blue-400 flex-shrink-0" />
            FinPulse
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Finance &amp; market headlines — keywords, quick insights, jump to NSE signal cards
          </p>
          {cachedAt && !loading && (
            <p className="text-xs text-gray-400 mt-1">
              Updated {new Date(cachedAt).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => load(true)}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 self-start px-3 py-2 rounded-lg text-sm font-medium
            bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200
            border border-gray-200 dark:border-gray-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {err && (
        <div className="rounded-xl border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/30 px-4 py-3 text-sm text-red-800 dark:text-red-300">
          {err}
        </div>
      )}

      {loading && !items.length && (
        <div className="space-y-4 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-40 rounded-2xl bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800"
            />
          ))}
        </div>
      )}

      {!loading && !items.length && !err && (
        <p className="text-center text-gray-400 text-sm py-16">No finance headlines matched the filter right now.</p>
      )}

      <div className="space-y-4">
        {items.map((item, idx) => (
          <article
            key={`${item.url || item.headline}-${idx}`}
            className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm dark:shadow-lg
              transition-shadow hover:shadow-md dark:hover:border-gray-700"
          >
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span
                className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full border ${
                  SENTIMENT_STYLES[item.sentiment] || SENTIMENT_STYLES.neutral
                }`}
              >
                {item.sentiment || 'neutral'}
              </span>
              {item.source && (
                <span className="text-xs text-gray-400">{item.source}</span>
              )}
            </div>

            <h3 className="text-lg font-bold text-gray-900 dark:text-white leading-snug mb-2">{item.headline}</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed line-clamp-4">{item.summary}</p>

            {item.keywords?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-4">
                {item.keywords.map((kw) => (
                  <span
                    key={`${kw}-${item.headline}`}
                    className="text-[11px] px-2 py-0.5 rounded-md bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            )}

            {item.matched_stocks?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {item.matched_stocks.map((st) => (
                  <button
                    key={st.symbol}
                    type="button"
                    onClick={() => goToStock(st.symbol)}
                    className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700
                      shadow-sm transition-colors"
                    title={st.yahoo_symbol ? `${st.label} (${st.yahoo_symbol})` : st.label}
                  >
                    {st.symbol}
                  </button>
                ))}
              </div>
            )}

            {item.insights?.length > 0 && (
              <ul className="mt-4 space-y-1.5 text-xs text-gray-500 dark:text-gray-400 border-t border-gray-100 dark:border-gray-800 pt-3">
                {item.insights.map((line, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-blue-500 flex-shrink-0">●</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            )}

            {item.url && (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-4 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
              >
                Read source <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </article>
        ))}
      </div>
    </div>
  )
}
