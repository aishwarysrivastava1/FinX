import axios from 'axios'

const _BASE = import.meta.env.VITE_API_URL || '/api'

const api = axios.create({
  baseURL: _BASE,
  timeout: 30000,
})

// Fast client for price-only endpoints — short timeout, no retry wait
const fastApi = axios.create({
  baseURL: _BASE,
  timeout: 5000,
})

let _authToken    = null
let _refreshToken = null
let _onLogout     = null
let _isRefreshing = false
let _failedQueue  = []

export const setAuthToken     = (t) => { _authToken = t }
export const getAuthToken     = ()  => _authToken
export const setRefreshToken  = (t) => { _refreshToken = t }
export const setLogoutHandler = (fn) => { _onLogout = fn }

// Unwrap { success, data } envelope used by v1 routes.
// v2 routes return plain objects — no envelope — so this is a no-op for them.
const _unwrap = (r) => {
  const body = r.data
  if (body && typeof body === 'object' && 'success' in body) {
    if (!body.success) return Promise.reject(new Error(body.error || 'Request failed'))
    return body.data
  }
  return body
}

const _onErr = (err) => {
  const msg =
    err.response?.data?.detail ||
    err.response?.data?.error  ||
    err.message                ||
    'Network error'
  return Promise.reject(new Error(msg))
}

// Process queued requests after a token refresh completes/fails
const _processQueue = (error, token = null) => {
  _failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token)))
  _failedQueue = []
}

// ── Main API interceptors ────────────────────────────────────────────────────

api.interceptors.request.use((config) => {
  if (_authToken) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${_authToken}`
  }
  return config
})

api.interceptors.response.use(_unwrap, async (error) => {
  const original = error.config

  // Attempt silent token refresh on 401 (once per request)
  if (error.response?.status === 401 && !original._retry && _refreshToken) {
    if (_isRefreshing) {
      // Queue concurrent requests until refresh completes
      return new Promise((resolve, reject) => {
        _failedQueue.push({ resolve, reject })
      }).then((token) => {
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      }).catch(Promise.reject.bind(Promise))
    }

    original._retry = true
    _isRefreshing   = true

    try {
      const res = await axios.post(`${_BASE}/v2/auth/refresh`, {
        refresh_token: _refreshToken,
      })
      const { access_token, refresh_token } = res.data
      _authToken    = access_token
      _refreshToken = refresh_token
      localStorage.setItem('finx_access',  access_token)
      localStorage.setItem('finx_refresh', refresh_token)
      _processQueue(null, access_token)
      original.headers.Authorization = `Bearer ${access_token}`
      return api(original)
    } catch (refreshErr) {
      _processQueue(refreshErr, null)
      _onLogout?.()
      return _onErr(error)
    } finally {
      _isRefreshing = false
    }
  }

  return _onErr(error)
})

// ── Fast API interceptors (price endpoints — no refresh) ─────────────────────

fastApi.interceptors.request.use((config) => {
  if (_authToken) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${_authToken}`
  }
  return config
})

fastApi.interceptors.response.use(_unwrap, _onErr)

// ── Named exports ────────────────────────────────────────────────────────────

export const fetchSignals      = (p = {})   => api.get('/signals',          { params: p })
export const refreshRadar      = ()         => api.post('/signals/refresh')
export const fetchSignalCard   = (sym, fr)  => api.get(`/card/${sym}`,      { params: { force_refresh: fr }, timeout: 60000 })
export const sendChatMessage   = (msg, sid) => api.post('/chat',            { message: msg, session_id: sid || null })
export const clearChat         = (sid)      => api.delete(`/chat/${sid}`)
export const pingHealth        = ()         => api.get('/health')
export const searchStocks      = (q)        => api.get('/search',           { params: { q } })
export const fetchMarketMovers = ()         => api.get('/market/movers')
export const fetchFinPulse     = (force)    => api.get('/finpulse',         { params: { force_refresh: force || false } })
export const fetchMarketStatus = ()         => api.get('/market/status')
export const fetchLiveQuote    = (sym)      => api.get(`/market/live/${sym}`)
export const fetchMarketChart  = (sym, p)   => api.get(`/market/chart/${sym}`, { params: { period: p } })
export const fetchQuickPrice   = (sym)      => fastApi.get(`/market/price/${sym}`)

export const getMarketWsUrl = (sym) => {
  const base   = _BASE
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const isAbs  = /^https?:\/\//i.test(base)
  const httpBase = isAbs ? base : `${origin}${base}`
  const wsBase   = httpBase.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:')
  return `${wsBase}/market/ws/${encodeURIComponent(sym)}`
}

export { api, fastApi }
