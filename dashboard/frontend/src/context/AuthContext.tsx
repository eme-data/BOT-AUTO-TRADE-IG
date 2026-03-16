import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react'

interface LoginResult {
  mfa_required: boolean
}

interface AuthContextType {
  token: string | null
  isAuthenticated: boolean
  needsSetup: boolean | null
  userRole: string
  isAdmin: boolean
  login: (username: string, password: string, totpCode?: string) => Promise<LoginResult>
  setup: (username: string, password: string) => Promise<void>
  logout: () => void
}

function parseRole(token: string | null): string {
  if (!token) return 'viewer'
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.role || 'admin'
  } catch { return 'admin' }
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'))
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null)
  const userRole = parseRole(token)
  const isAdmin = userRole === 'admin'

  useEffect(() => {
    checkStatus()
  }, [])

  const checkStatus = async () => {
    try {
      const res = await fetch('/api/auth/status')
      if (res.ok) {
        const data = await res.json()
        setNeedsSetup(data.needs_setup)
      }
    } catch {
      // server not ready
    }
  }

  const login = async (username: string, password: string, totpCode?: string): Promise<LoginResult> => {
    if (totpCode) {
      // Use JSON endpoint for MFA login
      const res = await fetch('/api/auth/login-mfa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, totp_code: totpCode }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Login failed')
      }
      const data = await res.json()
      if (data.mfa_required) {
        return { mfa_required: true }
      }
      localStorage.setItem('token', data.access_token)
      setToken(data.access_token)
      setNeedsSetup(false)
      return { mfa_required: false }
    }

    // Standard OAuth2 form login
    const body = new URLSearchParams({ username, password })
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Login failed')
    }
    const data = await res.json()
    if (data.mfa_required) {
      return { mfa_required: true }
    }
    localStorage.setItem('token', data.access_token)
    setToken(data.access_token)
    setNeedsSetup(false)
    return { mfa_required: false }
  }

  const setup = async (username: string, password: string) => {
    const res = await fetch('/api/auth/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Setup failed')
    }
    const data = await res.json()
    localStorage.setItem('token', data.access_token)
    setToken(data.access_token)
    setNeedsSetup(false)
  }

  const logout = () => {
    localStorage.removeItem('token')
    setToken(null)
  }

  return (
    <AuthContext.Provider
      value={{
        token,
        isAuthenticated: !!token,
        needsSetup,
        userRole,
        isAdmin,
        login,
        setup,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

/** Helper to make authenticated API calls */
export function useApiFetch() {
  const { token, logout } = useAuth()

  return useCallback(
    async (url: string, options: RequestInit = {}) => {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string>),
      }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
      const res = await fetch(url, { ...options, headers })
      if (res.status === 401) {
        logout()
        throw new Error('Session expired')
      }
      return res
    },
    [token, logout]
  )
}
