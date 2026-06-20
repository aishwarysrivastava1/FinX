import { useState, useEffect } from 'react'
import { Network } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

export default function ClusterRadar() {
  const [clusters, setClusters] = useState([])
  const [loading,  setLoading]  = useState(true)

  const fetchClusters = () => {
    fetch(`${API_BASE}/analytics/clusters`)
      .then(r => r.json())
      .then(data => {
        const fresh = data.clusters || []
        if (fresh.length > 0) setClusters(fresh)
        setLoading(false)
      })
      .catch(e => { console.error('[ClusterRadar]', e); setLoading(false) })
  }

  useEffect(() => {
    fetchClusters()
    const t = setInterval(fetchClusters, 60_000)
    return () => clearInterval(t)
  }, [])

  if (loading && clusters.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm animate-pulse">
        <div className="h-5 w-64 bg-gray-200 dark:bg-gray-700 rounded mb-4" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[1,2].map(i => <div key={i} className="h-24 bg-gray-100 dark:bg-gray-800 rounded-xl" />)}
        </div>
      </div>
    )
  }

  if (!loading && clusters.length === 0) return null

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <Network className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
        <h2 className="text-base font-bold text-gray-900 dark:text-white">Smart Money: High-Conviction Sector Clusters</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {clusters.map((c, i) => (
          <div key={i} className="bg-gray-50 dark:bg-gray-800/60 rounded-xl p-4 border border-gray-100 dark:border-gray-700/50">
            <div className="flex justify-between items-start mb-2">
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{c.sector}</span>
              <span className="bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-400 text-xs px-2 py-0.5 rounded-full border border-indigo-200 dark:border-indigo-700">
                {c.institution_count} Institutions
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-2">Notable buyers:</p>
            <div className="flex flex-wrap gap-1">
              {c.clients.map((client, j) => (
                <span key={j} className="text-xs bg-gray-200 dark:bg-gray-700/50 text-gray-700 dark:text-gray-300 px-1.5 py-0.5 rounded">
                  {client.substring(0, 15)}{client.length > 15 ? '…' : ''}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
