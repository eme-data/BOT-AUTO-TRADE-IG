import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { needsSetup, login, setup } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [mfaStep, setMfaStep] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const isSetup = needsSetup === true

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (isSetup && password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setLoading(true)
    try {
      if (isSetup) {
        await setup(username, password)
      } else if (mfaStep) {
        const result = await login(username, password, totpCode)
        if (result.mfa_required) {
          setError('Code TOTP invalide')
        }
      } else {
        const result = await login(username, password)
        if (result.mfa_required) {
          setMfaStep(true)
          setTotpCode('')
        }
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center px-4">
      <div className="card p-8 w-full max-w-md">
        <div className="text-center mb-6">
          <div className="flex items-center justify-center gap-3 mb-2">
            <svg width="32" height="32" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M20 4L36 12V28L20 36L4 28V12L20 4Z" fill="#DC2626" fillOpacity="0.15" stroke="#DC2626" strokeWidth="2"/>
              <path d="M20 10L30 16V26L20 32L10 26V16L20 10Z" fill="#DC2626" fillOpacity="0.3"/>
              <text x="20" y="24" textAnchor="middle" fill="#DC2626" fontSize="11" fontWeight="bold" fontFamily="Inter, sans-serif">A</text>
            </svg>
            <h1 className="text-2xl font-bold text-white">Altior</h1>
          </div>
          <p className="text-gray-500 text-sm mt-1">
            {isSetup ? 'Create your admin account' : mfaStep ? 'Enter your authenticator code' : 'Sign in to your dashboard'}
          </p>
        </div>

        {error && (
          <div className="bg-loss/20 text-loss text-sm rounded-lg px-4 py-2 mb-4">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {!mfaStep && (
            <>
              <div>
                <label className="block text-sm text-gray-500 mb-1">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="input"
                  required
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm text-gray-500 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input"
                  required
                  minLength={8}
                />
              </div>

              {isSetup && (
                <div>
                  <label className="block text-sm text-gray-500 mb-1">Confirm Password</label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="input"
                    required
                    minLength={8}
                  />
                </div>
              )}
            </>
          )}

          {mfaStep && (
            <div>
              <label className="block text-sm text-gray-500 mb-1">Code TOTP (6 chiffres)</label>
              <input
                type="text"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="input text-center text-2xl tracking-[0.5em] font-mono"
                placeholder="000000"
                maxLength={6}
                required
                autoFocus
                autoComplete="one-time-code"
              />
              <button
                type="button"
                className="text-xs text-gray-500 hover:text-gray-300 mt-2"
                onClick={() => { setMfaStep(false); setTotpCode(''); setError('') }}
              >
                Retour
              </button>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || (mfaStep && totpCode.length !== 6)}
            className="w-full btn-primary py-2.5 disabled:opacity-50"
          >
            {loading ? 'Please wait...' : isSetup ? 'Create Account' : mfaStep ? 'Verify' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
