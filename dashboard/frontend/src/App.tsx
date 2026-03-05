import { useState } from 'react'
import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import BotStatusIndicator from './components/BotStatusIndicator'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Trades from './pages/Trades'
import Settings from './pages/Settings'
import IGSettings from './pages/IGSettings'
import Markets from './pages/Markets'
import RiskSettings from './pages/RiskSettings'
import Logs from './pages/Logs'
import Notifications from './pages/Notifications'
import Backtest from './pages/Backtest'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, needsSetup } = useAuth()

  if (needsSetup === null) {
    return <div className="min-h-screen bg-bg-primary flex items-center justify-center text-gray-400">Loading...</div>
  }
  if (needsSetup || !isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function SettingsDropdown() {
  const [open, setOpen] = useState(false)
  const linkClass = 'block px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white'

  return (
    <div className="relative" onMouseLeave={() => setOpen(false)}>
      <button
        onClick={() => setOpen(!open)}
        className="text-sm font-medium text-gray-400 hover:text-white"
      >
        Config
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 bg-bg-secondary border border-gray-700 rounded-lg shadow-xl z-50 py-1">
          <NavLink to="/ig-settings" className={linkClass} onClick={() => setOpen(false)}>IG Account</NavLink>
          <NavLink to="/markets" className={linkClass} onClick={() => setOpen(false)}>Markets</NavLink>
          <NavLink to="/settings" className={linkClass} onClick={() => setOpen(false)}>Strategies</NavLink>
          <NavLink to="/risk" className={linkClass} onClick={() => setOpen(false)}>Risk & Bot</NavLink>
          <NavLink to="/notifications" className={linkClass} onClick={() => setOpen(false)}>Notifications</NavLink>
        </div>
      )}
    </div>
  )
}

function App() {
  const { isAuthenticated, needsSetup, logout } = useAuth()

  if (needsSetup === null) {
    return <div className="min-h-screen bg-bg-primary flex items-center justify-center text-gray-400">Loading...</div>
  }
  if (needsSetup || !isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `text-sm font-medium ${isActive ? 'text-blue-400' : 'text-gray-400 hover:text-white'}`

  return (
    <div className="min-h-screen bg-bg-primary">
      <nav className="bg-bg-secondary border-b border-gray-700 px-6 py-3">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold text-white">IG Trading Bot</span>
            <span className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded">v0.2</span>
            <BotStatusIndicator />
          </div>
          <div className="flex items-center gap-6">
            <NavLink to="/" end className={navLinkClass}>Dashboard</NavLink>
            <NavLink to="/trades" className={navLinkClass}>Trades</NavLink>
            <NavLink to="/backtest" className={navLinkClass}>Backtest</NavLink>
            <NavLink to="/logs" className={navLinkClass}>Logs</NavLink>
            <SettingsDropdown />
            <button
              onClick={logout}
              className="text-sm text-gray-500 hover:text-loss ml-2"
            >
              Logout
            </button>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-6">
        <Routes>
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/trades" element={<ProtectedRoute><Trades /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
          <Route path="/ig-settings" element={<ProtectedRoute><IGSettings /></ProtectedRoute>} />
          <Route path="/markets" element={<ProtectedRoute><Markets /></ProtectedRoute>} />
          <Route path="/risk" element={<ProtectedRoute><RiskSettings /></ProtectedRoute>} />
          <Route path="/backtest" element={<ProtectedRoute><Backtest /></ProtectedRoute>} />
          <Route path="/logs" element={<ProtectedRoute><Logs /></ProtectedRoute>} />
          <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
