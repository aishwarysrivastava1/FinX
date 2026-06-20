import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  Activity, BarChart3, MessageSquare, Newspaper,
  TrendingUp, Zap, Shield, Eye,
  ArrowRight, Sun, Moon, CheckCircle2
} from 'lucide-react'
import { useTheme } from '../context/ThemeContext'

const FEATURES = [
  {
    icon: Activity,
    title: 'Opportunity Radar',
    desc: 'Real-time NSE bulk & block deal detection. Track institutional smart money before the market reacts.',
    color: 'text-blue-500',
    ring: 'ring-blue-500/20',
    bg: 'bg-blue-500/10 dark:bg-blue-500/15',
  },
  {
    icon: BarChart3,
    title: 'AI Signal Cards',
    desc: 'Per-stock AI analysis: sentiment scoring, technical snapshot, news impact score, and risk flags.',
    color: 'text-violet-500',
    ring: 'ring-violet-500/20',
    bg: 'bg-violet-500/10 dark:bg-violet-500/15',
  },
  {
    icon: MessageSquare,
    title: 'Live Market Chat',
    desc: 'Ask anything. Answers grounded in live NSE prices, Nifty snapshot, and real-time radar signals.',
    color: 'text-emerald-500',
    ring: 'ring-emerald-500/20',
    bg: 'bg-emerald-500/10 dark:bg-emerald-500/15',
  },
  {
    icon: Newspaper,
    title: 'FinPulse Intelligence',
    desc: 'Finance news with AI sentiment, keyword extraction, and direct links to affected NSE stocks.',
    color: 'text-amber-500',
    ring: 'ring-amber-500/20',
    bg: 'bg-amber-500/10 dark:bg-amber-500/15',
  },
]

const STATS = [
  { value: '~99%', label: 'NSE Stocks' },
  { value: '3-Tier', label: 'AI Fallback' },
  { value: '<50ms', label: 'Price Latency' },
  { value: 'Live', label: 'WebSocket Feed' },
]

const TRUST = [
  'NSE bulk & block deal data',
  'Groq (Llama-3.3-70b-versatile)',
  'Backtested signal win rates',
  'Educational use — no SEBI advice',
]

// Google "G" SVG icon
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4" />
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853" />
      <path d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z" fill="#FBBC05" />
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 7.293C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335" />
    </svg>
  )
}

export default function LandingPage({ onAuthed }) {
  const { login, signup } = useAuth()
  const { dark, toggle } = useTheme()

  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [checkEmail, setCheckEmail] = useState(false)
  const [emailSent, setEmailSent] = useState(true)
  const [fallbackLink, setFallbackLink] = useState('')
  const [verifyStatus, setVerifyStatus] = useState(null) // 'success' | 'error' | null

  // ── Handle email verification redirect: /?verified=success|error ──────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const v = params.get('verified')
    if (!v) return
    window.history.replaceState({}, '', window.location.pathname)
    setVerifyStatus(v === 'success' ? 'ok' : 'fail')
  }, [])

  // ── Handle Google OAuth callback: /?access_token=...&auth=google ──────────
  // Tokens are consumed by AuthContext — if user is now authed, App re-renders
  // and LandingPage unmounts. Nothing extra to do here.

  const submit = async (e) => {
    e?.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'register') {
        const res = await signup({ email, password })
        setEmailSent(res?.email_sent !== false)
        setFallbackLink(res?.verification_link || '')
        setCheckEmail(true)
      } else {
        await login({ email, password })
        onAuthed?.()
      }
    } catch (err) {
      setError(err?.message || 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  const googleLoginUrl = `${import.meta.env.VITE_API_URL}/v2/auth/google/login`

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col transition-colors duration-200">

      {/* ── Top bar ── */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-violet-600 rounded-xl flex items-center justify-center shadow-md">
            <span className="text-white text-xs font-extrabold tracking-tight">FX</span>
          </div>
          <span className="font-extrabold text-gray-900 dark:text-white text-lg tracking-tight">Fin-X</span>
          <span className="hidden sm:inline text-xs text-gray-400 border-l border-gray-200 dark:border-gray-700 pl-2">NSE Intelligence</span>
        </div>
        <button
          onClick={toggle}
          className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">

          {/* ── Left: Hero + Features ── */}
          <div className="space-y-8">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800/50 rounded-full px-3 py-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-xs font-semibold text-blue-700 dark:text-blue-300">ET Hackathon — AI Fintech Track</span>
            </div>

            {/* Headline */}
            <div className="space-y-3">
              <h1 className="text-4xl sm:text-5xl font-extrabold text-gray-900 dark:text-white leading-tight tracking-tight">
                India's AI-Powered
                <br />
                <span className="bg-gradient-to-r from-blue-600 to-violet-600 bg-clip-text text-transparent">
                  Market Intelligence
                </span>
              </h1>
              <p className="text-lg text-gray-500 dark:text-gray-400 leading-relaxed max-w-lg">
                Real-time NSE signals, institutional deal tracking, and AI-driven analysis — all in one place. Built for serious retail investors.
              </p>
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-4 gap-3">
              {STATS.map(({ value, label }) => (
                <div key={label} className="text-center p-3 rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-sm">
                  <p className="text-base font-extrabold text-gray-900 dark:text-white tabular-nums">{value}</p>
                  <p className="text-[10px] text-gray-500 dark:text-gray-500 mt-0.5 leading-tight">{label}</p>
                </div>
              ))}
            </div>

            {/* Feature grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {FEATURES.map(({ icon: Icon, title, desc, color, bg, ring }) => (
                <div
                  key={title}
                  className="flex gap-3 p-4 rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 hover:shadow-md transition-shadow duration-200"
                >
                  <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ring-1 ${ring} ${bg}`}>
                    <Icon className={`w-4.5 h-4.5 ${color}`} style={{ width: 18, height: 18 }} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-gray-900 dark:text-white mb-0.5">{title}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{desc}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Trust bullets */}
            <div className="grid grid-cols-2 gap-x-6 gap-y-2">
              {TRUST.map(t => (
                <div key={t} className="flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                  <span className="text-xs text-gray-500 dark:text-gray-400">{t}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Right: Auth Card ── */}
          <div className="w-full max-w-md mx-auto lg:mx-0 lg:ml-auto">
            <div className="bg-white dark:bg-gray-900 rounded-3xl border border-gray-200 dark:border-gray-800 shadow-2xl dark:shadow-gray-900/50 overflow-hidden">

              {/* Gradient strip */}
              <div className="h-1.5 bg-gradient-to-r from-blue-600 via-violet-600 to-blue-600" />

              <div className="p-8">

                {/* ── Email verified: success ── */}
                {verifyStatus === 'ok' && (
                  <div className="text-center space-y-4 py-4">
                    <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center mx-auto">
                      <CheckCircle2 className="w-8 h-8 text-emerald-500" />
                    </div>
                    <div>
                      <p className="text-xl font-bold text-gray-900 dark:text-white mb-1">Email Verified!</p>
                      <p className="text-sm text-gray-500">Your account is active. You can now log in.</p>
                    </div>
                    <button
                      onClick={() => setVerifyStatus(null)}
                      className="w-full bg-blue-600 hover:bg-blue-500 text-white rounded-xl px-4 py-3 text-sm font-semibold transition-colors"
                    >
                      Go to Login
                    </button>
                  </div>
                )}

                {/* ── Email verified: error ── */}
                {verifyStatus === 'fail' && (
                  <div className="text-center space-y-4 py-4">
                    <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mx-auto">
                      <Shield className="w-8 h-8 text-red-500" />
                    </div>
                    <div>
                      <p className="text-xl font-bold text-gray-900 dark:text-white mb-1">Invalid Link</p>
                      <p className="text-sm text-gray-500">This link is invalid or already used. Try signing up again.</p>
                    </div>
                    <button
                      onClick={() => { setVerifyStatus(null); setMode('register') }}
                      className="w-full bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-xl px-4 py-3 text-sm font-semibold transition-colors"
                    >
                      Back to Sign Up
                    </button>
                  </div>
                )}

                {/* ── Check your email screen ── */}
                {!verifyStatus && checkEmail && (
                  <div className="text-center space-y-4 py-4">
                    <div className="w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center mx-auto">
                      <Zap className="w-8 h-8 text-blue-500" />
                    </div>
                    <div>
                      <p className="text-xl font-bold text-gray-900 dark:text-white mb-1">Check Your Email</p>
                      {emailSent ? (
                        <p className="text-sm text-gray-500">
                          We sent a verification link to{' '}
                          <span className="font-semibold text-gray-700 dark:text-gray-300">{email}</span>.
                          Click it to activate your account.
                        </p>
                      ) : (
                        <p className="text-sm text-gray-500">SMTP not configured. Use the link below for local testing.</p>
                      )}
                    </div>
                    {!emailSent && fallbackLink && (
                      <a
                        href={fallbackLink}
                        className="block p-3 rounded-xl bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs break-all text-left text-blue-600 dark:text-blue-400 font-mono hover:underline"
                      >
                        {fallbackLink}
                      </a>
                    )}
                    <button
                      onClick={() => { setCheckEmail(false); setMode('login') }}
                      className="w-full bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-xl px-4 py-3 text-sm font-semibold transition-colors flex items-center justify-center gap-2"
                    >
                      <ArrowRight className="w-4 h-4" />
                      Back to Login
                    </button>
                  </div>
                )}

                {/* ── Main auth form ── */}
                {!verifyStatus && !checkEmail && (
                  <>
                    <div className="mb-6">
                      <h2 className="text-2xl font-extrabold text-gray-900 dark:text-white">
                        {mode === 'login' ? 'Welcome back' : 'Create account'}
                      </h2>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        {mode === 'login'
                          ? 'Sign in to your Fin-X account'
                          : 'Start tracking institutional signals'}
                      </p>
                    </div>

                    {/* Mode toggle */}
                    <div className="flex bg-gray-100 dark:bg-gray-800 rounded-xl p-1 mb-6">
                      {['login', 'register'].map(m => (
                        <button
                          key={m}
                          onClick={() => { setMode(m); setError('') }}
                          className={`flex-1 py-2 rounded-lg text-sm font-semibold capitalize transition-all duration-150
                            ${mode === m
                              ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                            }`}
                        >
                          {m === 'login' ? 'Log In' : 'Sign Up'}
                        </button>
                      ))}
                    </div>

                    {/* Google OAuth button */}
                    <a
                      href={googleLoginUrl}
                      className="w-full flex items-center justify-center gap-3 px-4 py-3 mb-4
                        rounded-xl border border-gray-200 dark:border-gray-700
                        bg-white dark:bg-gray-800
                        hover:bg-gray-50 dark:hover:bg-gray-750
                        text-sm font-semibold text-gray-700 dark:text-gray-200
                        transition-colors shadow-sm"
                    >
                      <GoogleIcon />
                      Continue with Google
                    </a>

                    {/* Divider */}
                    <div className="flex items-center gap-3 mb-4">
                      <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                      <span className="text-xs text-gray-400 dark:text-gray-500">or</span>
                      <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                    </div>

                    {/* Email / Password form */}
                    <form onSubmit={submit} className="space-y-4">
                      <div>
                        <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300 mb-1.5">Email address</label>
                        <input
                          value={email}
                          onChange={e => setEmail(e.target.value)}
                          type="email"
                          placeholder="you@example.com"
                          required
                          className="w-full bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-gray-600 dark:text-gray-300 mb-1.5">Password</label>
                        <input
                          value={password}
                          onChange={e => setPassword(e.target.value)}
                          type="password"
                          placeholder={mode === 'register' ? 'Min 8 chars, A-Z, 0-9, special char' : '••••••••'}
                          required
                          minLength={8}
                          className="w-full bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all"
                        />
                        {mode === 'register' && (
                          <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-1.5">
                            Must include uppercase, lowercase, number &amp; special character (!@#$…)
                          </p>
                        )}
                      </div>

                      {error && (
                        <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800/50 rounded-xl px-4 py-3">
                          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
                        </div>
                      )}

                      <button
                        type="submit"
                        disabled={loading || !email || !password}
                        className="w-full bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500
                          disabled:from-gray-300 disabled:to-gray-300 dark:disabled:from-gray-700 dark:disabled:to-gray-700
                          disabled:cursor-not-allowed text-white rounded-xl px-4 py-3.5 text-sm font-bold
                          transition-all duration-150 shadow-sm hover:shadow-blue-500/25 hover:shadow-lg
                          flex items-center justify-center gap-2 mt-2"
                      >
                        {loading ? (
                          <span className="flex items-center gap-2">
                            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            Please wait…
                          </span>
                        ) : (
                          <span className="flex items-center gap-2">
                            {mode === 'login' ? 'Sign In' : 'Create Account'}
                            <ArrowRight className="w-4 h-4" />
                          </span>
                        )}
                      </button>
                    </form>

                    <p className="text-center text-xs text-gray-400 dark:text-gray-600 mt-5">
                      {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
                      <button
                        onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
                        className="text-blue-600 dark:text-blue-400 font-semibold hover:underline"
                      >
                        {mode === 'login' ? 'Sign up free' : 'Log in'}
                      </button>
                    </p>
                  </>
                )}
              </div>
            </div>

            {/* Below card note */}
            <p className="text-center text-xs text-gray-400 dark:text-gray-600 mt-4">
              For educational purposes only · Not SEBI-registered investment advice
            </p>
          </div>

        </div>
      </main>

      {/* ── Footer ── */}
      <footer className="text-center text-xs text-gray-400 dark:text-gray-600 py-4 border-t border-gray-200 dark:border-gray-900">
        Fin-X · NSE Market Intelligence · Data: NSE India
      </footer>
    </div>
  )
}
