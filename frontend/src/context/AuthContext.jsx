import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react'
import { api, setAuthToken, setRefreshToken as setApiRefreshToken, setLogoutHandler } from '../api'

const AuthContext = createContext(null)

const ACCESS_KEY = 'finx_access'
const REFRESH_KEY = 'finx_refresh'

export function useAuth() {
  return useContext(AuthContext)
}

export default function AuthProvider({ children }) {
  const [accessToken, setAccessToken] = useState(() => localStorage.getItem(ACCESS_KEY) || null)
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)   // true until first session check completes

  // ── Persist tokens ────────────────────────────────────────────────────────
  const storeTokens = useCallback((access, refresh) => {
    setAccessToken(access)
    setAuthToken(access)
    setApiRefreshToken(refresh)
    if (access) localStorage.setItem(ACCESS_KEY, access)
    else localStorage.removeItem(ACCESS_KEY)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
    else localStorage.removeItem(REFRESH_KEY)
  }, [])

  // ── Logout ────────────────────────────────────────────────────────────────
  const logout = useCallback(() => {
    storeTokens(null, null)
    setUser(null)
  }, [storeTokens])

  // Register logout handler so API refresh interceptor can call it on expiry
  useEffect(() => { setLogoutHandler(logout) }, [logout])

  // On mount: seed API client from localStorage
  useEffect(() => {
    const access = localStorage.getItem(ACCESS_KEY)
    const refresh = localStorage.getItem(REFRESH_KEY)
    setAuthToken(access)
    setApiRefreshToken(refresh)
  }, [])

  // ── Fetch current user ────────────────────────────────────────────────────
  const fetchMe = useCallback(async () => {
    try {
      const me = await api.get('/v2/auth/me')
      setUser(me)
    } catch {
      logout()
    } finally {
      setIsLoading(false)
    }
  }, [logout])

  // Restore session on initial load — clears loading when done
  useEffect(() => {
    if (accessToken) {
      fetchMe()
    } else {
      setIsLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Google OAuth callback ─────────────────────────────────────────────────
  // Backend redirects to /?access_token=...&refresh_token=...&auth=google
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('auth') !== 'google') return
    const access = params.get('access_token')
    const refresh = params.get('refresh_token')
    if (!access || !refresh) return
    window.history.replaceState({}, '', window.location.pathname)
    storeTokens(access, refresh)
    api.get('/v2/auth/me')
      .then(setUser)
      .catch(() => logout())
      .finally(() => setIsLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Context value ─────────────────────────────────────────────────────────
  const value = useMemo(() => {
    const isAuthed = !!accessToken

    const login = async ({ email, password }) => {
      const res = await api.post('/v2/auth/login', { email, password })
      const access = res?.access_token
      const refresh = res?.refresh_token
      if (!access) throw new Error('Login succeeded but no token returned')
      storeTokens(access, refresh)
      api.get('/v2/auth/me').then(setUser).catch(() => { })
      return true
    }

    // Returns { registered, email_sent, verification_link }
    const signup = async ({ email, password }) => {
      return await api.post('/v2/auth/signup', { email, password })
    }

    return { accessToken, user, isAuthed, isLoading, login, signup, logout, fetchMe }
  }, [accessToken, user, isLoading, logout, fetchMe, storeTokens])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
