import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Trash2, Loader2, Sparkles } from 'lucide-react'
import { sendChatMessage, clearChat } from '../api'

const isHeadingLine = (line) =>
  line.startsWith('**') ||           // markdown bold (older responses)
  /^[\u{1D400}-\u{1D7FF}]/u.test(line); // unicode bold letters


const QUICK = [
  'Why is Nifty moving today?',
  'What are bulk deals and why do they matter?',
  'Explain RSI in simple terms',
  'How do FII flows affect Indian markets?',
  'What does an EMA crossover signal mean?',
  'Which sectors are performing well this week?',
]

const WELCOME = {
  role: 'assistant',
  content: "Hi! I'm your Fin-X AI Market Assistant. I have access to live NSE data, today's bulk deals, and recent market headlines.\n\nAsk me anything about Indian stocks and markets!"
}

const CHAT_STORAGE_KEY = 'finx_market_chat_history'

function readStoredChat() {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    const messages = Array.isArray(parsed) ? parsed : parsed.messages
    const sessionId = Array.isArray(parsed) ? null : (parsed.sessionId ?? null)
    if (!Array.isArray(messages)) return null
    if (!messages.every(m => m && typeof m.role === 'string' && typeof m.content === 'string')) return null
    return { messages, sessionId }
  } catch {
    return null
  }
}

function Msg({ role, content }) {
  const isUser = role === 'user'
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm
        ${isUser ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'}`}>
        {isUser
          ? <User className="w-4 h-4 text-white" />
          : <Bot className="w-4 h-4 text-blue-600 dark:text-blue-400" />
        }
      </div>
      <div className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap shadow-sm
        ${isUser
          ? 'bg-blue-600 text-white rounded-tr-sm'
          : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-tl-sm border border-gray-200 dark:border-gray-700/50'
        }`}>
        {content.split('\n').map((ln, i) => {
          const trimmed = ln.trim()
          if (!trimmed) return <div key={i} style={{ height: 4 }} />
          const heading = isHeadingLine(trimmed)
          const text = trimmed.replace(/^\*+\s*/, '').replace(/^\**(.*?)\**$/, '$1')
          return (
            <div
              key={i}
              className={heading ? 'text-sm font-bold' : 'text-xs'}
              style={heading ? { fontSize: '0.95rem' } : {}}
            >
              {text}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Typing() {
  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center shadow-sm">
        <Bot className="w-4 h-4 text-blue-600 dark:text-blue-400" />
      </div>
      <div className="bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700/50 rounded-2xl rounded-tl-sm px-4 py-3.5">
        <div className="flex gap-1.5 items-center">
          {[0, 150, 300].map(d => (
            <div key={d} className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
          ))}
        </div>
      </div>
    </div>
  )
}

export default function ChatInterface() {
  const initRef = useRef(null)
  if (initRef.current === null) {
    initRef.current = readStoredChat()
  }
  const [msgs, setMsgs] = useState(() => initRef.current?.messages ?? [WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSession] = useState(() => initRef.current?.sessionId ?? null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    try {
      localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify({ messages: msgs, sessionId }))
    } catch { /* ignore quota / private mode */ }
  }, [msgs, sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs, loading])

  const send = async (text) => {
    const m = (text || input).trim()
    if (!m || loading) return
    setInput('')
    setMsgs(p => [...p, { role: 'user', content: m }])
    setLoading(true)
    try {
      const res = await sendChatMessage(m, sessionId)
      setSession(res.session_id)
      setMsgs(p => [...p, { role: 'assistant', content: res.reply }])
    } catch {
      setMsgs(p => [...p, { role: 'assistant', content: "I'm having trouble connecting right now. Please try again in a moment." }])
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  const handleClear = async () => {
    if (sessionId) await clearChat(sessionId).catch(() => { })
    try { localStorage.removeItem(CHAT_STORAGE_KEY) } catch { /* ignore */ }
    setMsgs([WELCOME])
    setSession(null)
  }

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 148px)', minHeight: '520px' }}>

      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center shadow-md">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <h2 className="text-base font-bold text-gray-900 dark:text-white">AI Market Assistant</h2>
            <p className="text-xs text-gray-500">Live NSE data · Indian market intelligence</p>
          </div>
        </div>
        <button
          onClick={handleClear}
          className="flex items-center gap-1.5 px-3 py-1.5 text-gray-400 hover:text-red-500 text-xs rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Clear
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 py-4 pr-1">
        {msgs.map((m, i) => <Msg key={i} {...m} />)}
        {loading && <Typing />}
        <div ref={bottomRef} />
      </div>

      {/* Quick questions */}
      {msgs.length <= 2 && !loading && (
        <div className="py-3 flex flex-wrap gap-2">
          {QUICK.map(q => (
            <button
              key={q}
              onClick={() => send(q)}
              className="text-xs px-3 py-1.5 bg-gray-100 dark:bg-gray-800 hover:bg-blue-50 dark:hover:bg-blue-900/40
                border border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700
                text-gray-600 dark:text-gray-300 hover:text-blue-700 dark:hover:text-white rounded-full transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="pt-3 border-t border-gray-200 dark:border-gray-800 flex gap-2">
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="Ask about any NSE stock, bulk deals, Nifty, RSI..."
          disabled={loading}
          className="flex-1 bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-2.5 text-sm
            text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500
            focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20
            disabled:opacity-50 transition-colors"
        />
        <button
          onClick={() => send()}
          disabled={!input.trim() || loading}
          className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-200 dark:disabled:bg-gray-700
            disabled:text-gray-400 rounded-xl text-white transition-colors flex-shrink-0"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </div>
    </div>
  )
}
