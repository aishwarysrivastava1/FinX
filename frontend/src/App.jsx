import { useState } from 'react'
import { ThemeProvider } from './context/ThemeContext'
import AuthProvider, { useAuth } from './context/AuthContext'
import Navbar from './components/Navbar'
import RadarPage from './pages/RadarPage'
import CardPage from './pages/CardPage'
import ChatPage from './pages/ChatPage'
import FinPulsePage from './pages/FinPulsePage'
import MarketWrapButton from './components/MarketWrapButton'
import WarmupBanner from './components/WarmupBanner'
import LandingPage from './pages/LandingPage'

function AppInner() {
  const { isAuthed, isLoading } = useAuth()
  const [page, setPage]            = useState('radar')
  const [selectedSym, setSelected] = useState('')

  // Prevent flash of login page while restoring saved session
  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-violet-600 rounded-2xl flex items-center justify-center shadow-lg">
            <span className="text-white text-sm font-extrabold">FX</span>
          </div>
          <div className="w-6 h-6 border-2 border-blue-600/30 border-t-blue-600 rounded-full animate-spin" />
        </div>
      </div>
    )
  }

  if (!isAuthed) {
    return <LandingPage onAuthed={() => setPage('radar')} />
  }

  const handleSelectStock = (symbol) => {
    setSelected(symbol)
    setPage('card')
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100 flex flex-col transition-colors duration-200">
      <Navbar active={page} onNav={setPage} />
      <div className="max-w-6xl w-full mx-auto px-4">
        <WarmupBanner />
      </div>
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        {page === 'radar'    && <RadarPage onSelectStock={handleSelectStock} />}
        {page === 'card'     && <CardPage initialSym={selectedSym} />}
        {page === 'chat'     && <ChatPage />}
        {page === 'finpulse' && <FinPulsePage onSelectStock={handleSelectStock} />}
      </main>
      <MarketWrapButton />
      <footer className="text-center text-xs text-gray-400 dark:text-gray-600 py-3 border-t border-gray-200 dark:border-gray-900">
        Fin-X — For educational purposes only. Not SEBI-registered investment advice. Data: NSE India
      </footer>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    </ThemeProvider>
  )
}
