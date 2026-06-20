import { useState, useEffect } from 'react'
import { Square, Volume2, Loader2 } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

export default function MarketWrapButton() {
  const [playing,  setPlaying]  = useState(false)
  const [script,   setScript]   = useState(null)
  const [fetching, setFetching] = useState(false)

  useEffect(() => {
    return () => { if ('speechSynthesis' in window) window.speechSynthesis.cancel() }
  }, [])

  const speak = (text) => {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const utt = new SpeechSynthesisUtterance(text)
    utt.rate  = 1.0
    const voices = window.speechSynthesis.getVoices()
    const voice  = voices.find(v => v.lang.startsWith('en'))
    if (voice) utt.voice = voice
    utt.onstart = () => setPlaying(true)
    utt.onend   = () => setPlaying(false)
    utt.onerror = () => setPlaying(false)
    window.speechSynthesis.speak(utt)
  }

  const handlePlay = async () => {
    if (playing) { window.speechSynthesis.cancel(); setPlaying(false); return }
    if (script)  { speak(script); return }
    setFetching(true)
    try {
      const res  = await fetch(`${API_BASE}/audio/market-minutes`)
      const data = await res.json()
      const text = data.script || data.data?.script || ''
      if (!text) throw new Error('empty script')
      setScript(text)
      speak(text)
    } catch {
      speak('Market minute service is currently unavailable.')
    } finally {
      setFetching(false)
    }
  }

  return (
    <button
      onClick={handlePlay}
      disabled={fetching}
      title="AI Market Minutes audio briefing"
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 rounded-full
        shadow-2xl transition-all duration-200 font-semibold text-sm text-white
        border disabled:opacity-70 disabled:cursor-not-allowed
        ${playing
          ? 'bg-red-600 hover:bg-red-500 border-red-500/30 animate-pulse'
          : 'bg-blue-700 hover:bg-blue-600 border-blue-500/20'
        }`}
    >
      {fetching  ? <Loader2 className="w-4 h-4 animate-spin" />
       : playing ? <Square  className="w-4 h-4" fill="currentColor" />
                 : <Volume2 className="w-4 h-4" />
      }
      <span className="hidden sm:inline">
        {fetching ? 'Loading…' : playing ? 'Stop' : 'Market Wrap'}
      </span>
    </button>
  )
}
