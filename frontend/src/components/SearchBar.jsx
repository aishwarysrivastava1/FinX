import { useState, useEffect, useRef, useCallback } from 'react'
import { Search, Loader2, X } from 'lucide-react'
import { searchStocks } from '../api'

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function SearchBar({ onSelect, placeholder = 'Search any NSE stock — e.g. Reliance, TCS, etc…' }) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const inputRef = useRef(null)
  const wrapRef = useRef(null)
  const debouncedQ = useDebounce(query, 280)

  useEffect(() => {
    if (!debouncedQ.trim()) { setSuggestions([]); setOpen(false); return }
    let cancelled = false
    setLoading(true)
    searchStocks(debouncedQ)
      .then(data => {
        if (cancelled) return
        setSuggestions(data?.results || [])
        setOpen(true)
        setActiveIdx(-1)
      })
      .catch(() => { if (!cancelled) setSuggestions([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [debouncedQ])

  useEffect(() => {
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = useCallback((item) => {
    setQuery(item.symbol)
    setOpen(false)
    setSuggestions([])
    onSelect?.(item.symbol)
  }, [onSelect])

  const handleKeyDown = (e) => {
    if (!open || !suggestions.length) {
      if (e.key === 'Enter' && query.trim()) { onSelect?.(query.trim().toUpperCase()); setOpen(false) }
      return
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, suggestions.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, -1)) }
    else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIdx >= 0) handleSelect(suggestions[activeIdx])
      else if (query.trim()) { onSelect?.(query.trim().toUpperCase()); setOpen(false) }
    } else if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div ref={wrapRef} className="relative w-full">
      <div className="flex items-center gap-3 bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700
                      rounded-xl px-4 py-3 focus-within:border-blue-500 focus-within:ring-1
                      focus-within:ring-blue-500/20 transition-all duration-150 shadow-sm">
        {loading
          ? <Loader2 className="w-4 h-4 text-gray-400 animate-spin flex-shrink-0" />
          : <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
        }
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length && setOpen(true)}
          placeholder={placeholder}
          className="flex-1 bg-transparent text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none"
          autoComplete="off"
          spellCheck="false"
        />
        {query && (
          <button
            onClick={() => { setQuery(''); setSuggestions([]); setOpen(false); inputRef.current?.focus() }}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {open && suggestions.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1.5 z-50
                        bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700
                        rounded-xl shadow-xl overflow-hidden">
          {suggestions.map((item, idx) => (
            <button
              key={item.symbol}
              onMouseDown={e => { e.preventDefault(); handleSelect(item) }}
              onMouseEnter={() => setActiveIdx(idx)}
              className={`w-full text-left px-4 py-3 flex items-center justify-between gap-3 transition-colors
                ${idx === activeIdx ? 'bg-blue-50 dark:bg-blue-600/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/60'}
                ${idx !== 0 ? 'border-t border-gray-100 dark:border-gray-700/50' : ''}`}
            >
              <div className="min-w-0">
                <p className="text-sm font-bold text-gray-900 dark:text-white">{item.symbol}</p>
                <p className="text-xs text-gray-500 truncate">{item.name}</p>
              </div>
              <span className="text-[10px] text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full flex-shrink-0">
                NSE
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
