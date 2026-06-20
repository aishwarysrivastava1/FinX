import { Activity, BarChart2, MessageSquare, Newspaper, Sun, Moon, LogOut } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'
import { useAuth } from '../context/AuthContext'

const TABS = [
  { id: 'radar',    label: 'Radar',       icon: Activity },
  { id: 'card',     label: 'Signal Card', icon: BarChart2 },
  { id: 'finpulse', label: 'FinPulse',    icon: Newspaper },
  { id: 'chat',     label: 'Market Chat', icon: MessageSquare },
]

export default function Navbar({ active, onNav }) {
  const { dark, toggle } = useTheme()
  const { user, logout } = useAuth()

  return (
    <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 sticky top-0 z-50 shadow-sm">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between gap-4">

        {/* Logo */}
        <div className="flex items-center gap-2.5 flex-shrink-0">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-violet-600 rounded-xl flex items-center justify-center shadow-md">
            <span className="text-white text-xs font-extrabold tracking-tight">FX</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-extrabold text-gray-900 dark:text-white text-lg tracking-tight">Fin-X</span>
            <span className="text-gray-400 dark:text-gray-600 text-xs hidden sm:block border-l border-gray-200 dark:border-gray-700 pl-2">
              NSE Intelligence
            </span>
          </div>
        </div>

        {/* Nav tabs */}
        <div className="flex items-center gap-1 flex-1 justify-center">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => onNav(id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150
                ${active === id
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="hidden md:inline">{label}</span>
            </button>
          ))}
        </div>

        {/* Right controls */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* User avatar + name/email */}
          {user && (() => {
            const initials = user.name
              ? user.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
              : (user.email?.[0] ?? '?').toUpperCase()
            const label = user.name || user.email
            return (
              <div className="hidden lg:flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center flex-shrink-0">
                  <span className="text-white text-[10px] font-bold leading-none">{initials}</span>
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-2.5 py-1 rounded-full border border-gray-200 dark:border-gray-700 max-w-[140px] truncate">
                  {label}
                </span>
              </div>
            )
          })()}

          {/* Theme toggle */}
          <button
            onClick={toggle}
            title={dark ? 'Switch to Light mode' : 'Switch to Dark mode'}
            className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors duration-150"
          >
            {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>

          {/* Logout */}
          <button
            onClick={logout}
            title="Log out"
            className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors duration-150"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </nav>
  )
}
