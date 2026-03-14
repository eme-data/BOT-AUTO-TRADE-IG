import { useState, useEffect, useCallback } from 'react'
import { useApiFetch } from '../context/AuthContext'

interface User {
  id: number
  username: string
  created_at: string | null
}

export default function UserManagement() {
  const apiFetch = useApiFetch()
  const [users, setUsers] = useState<User[]>([])
  const [currentUsername, setCurrentUsername] = useState('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Create user form
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [creating, setCreating] = useState(false)

  // Change password form
  const [currentPassword, setCurrentPassword] = useState('')
  const [nextPassword, setNextPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [changingPw, setChangingPw] = useState(false)

  // Delete confirmation
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)

  // MFA state
  const [mfaEnabled, setMfaEnabled] = useState(false)
  const [mfaSetupData, setMfaSetupData] = useState<{ secret: string; qr_code: string } | null>(null)
  const [mfaCode, setMfaCode] = useState('')
  const [mfaLoading, setMfaLoading] = useState(false)

  const loadUsers = useCallback(async () => {
    try {
      const res = await apiFetch('/api/users')
      if (res.ok) setUsers(await res.json())
    } catch { /* */ }
  }, [apiFetch])

  const loadMe = useCallback(async () => {
    try {
      const res = await apiFetch('/api/auth/me')
      if (res.ok) {
        const data = await res.json()
        setCurrentUsername(data.username)
        setMfaEnabled(data.mfa_enabled || false)
      }
    } catch { /* */ }
  }, [apiFetch])

  useEffect(() => {
    loadUsers()
    loadMe()
  }, [loadUsers, loadMe])

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (newPassword.length < 8) {
      setMessage({ type: 'error', text: 'Password must be at least 8 characters' })
      return
    }
    setCreating(true)
    setMessage(null)
    try {
      const res = await apiFetch('/api/users', {
        method: 'POST',
        body: JSON.stringify({ username: newUsername, password: newPassword }),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: `User '${newUsername}' created` })
        setNewUsername('')
        setNewPassword('')
        loadUsers()
      } else {
        const err = await res.json()
        setMessage({ type: 'error', text: err.detail || 'Create failed' })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (userId: number) => {
    if (confirmDeleteId !== userId) {
      setConfirmDeleteId(userId)
      return
    }
    setConfirmDeleteId(null)
    setMessage(null)
    try {
      const res = await apiFetch(`/api/users/${userId}`, { method: 'DELETE' })
      if (res.ok) {
        setMessage({ type: 'success', text: 'User deleted' })
        loadUsers()
      } else {
        const err = await res.json()
        setMessage({ type: 'error', text: err.detail || 'Delete failed' })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    }
  }

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (nextPassword !== confirmPassword) {
      setMessage({ type: 'error', text: 'New passwords do not match' })
      return
    }
    if (nextPassword.length < 8) {
      setMessage({ type: 'error', text: 'Password must be at least 8 characters' })
      return
    }
    setChangingPw(true)
    setMessage(null)
    try {
      const res = await apiFetch('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: nextPassword,
        }),
      })
      if (res.ok) {
        setMessage({ type: 'success', text: 'Password changed successfully' })
        setCurrentPassword('')
        setNextPassword('')
        setConfirmPassword('')
      } else {
        const err = await res.json()
        setMessage({ type: 'error', text: err.detail || 'Change failed' })
      }
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setChangingPw(false)
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-semibold text-white">User Management</h1>

      {message && (
        <div className={`rounded-lg px-4 py-2 text-sm ${
          message.type === 'success' ? 'bg-profit/20 text-profit' : 'bg-loss/20 text-loss'
        }`}>
          {message.text}
        </div>
      )}

      {/* User list */}
      <div className="card p-6">
        <h2 className="section-title mb-4">Admin Users</h2>
        <div className="space-y-2">
          {users.map((u) => (
            <div key={u.id} className="flex items-center justify-between py-2 px-3 rounded-lg bg-bg-primary">
              <div>
                <span className="text-white font-medium">{u.username}</span>
                {u.username === currentUsername && (
                  <span className="text-xs text-blue-400 ml-2">(you)</span>
                )}
                {u.created_at && (
                  <span className="text-xs text-gray-500 ml-3">
                    {new Date(u.created_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              <button
                onClick={() => handleDelete(u.id)}
                disabled={u.username === currentUsername}
                className={`text-xs px-3 py-1 rounded-lg transition-colors ${
                  u.username === currentUsername
                    ? 'text-gray-600 cursor-not-allowed'
                    : confirmDeleteId === u.id
                      ? 'bg-loss text-white'
                      : 'bg-loss/20 text-loss hover:bg-loss/30'
                }`}
              >
                {confirmDeleteId === u.id ? 'Confirm?' : 'Delete'}
              </button>
            </div>
          ))}
          {users.length === 0 && (
            <p className="text-sm text-gray-500">No users found</p>
          )}
        </div>
      </div>

      {/* Add new user */}
      <div className="card p-6">
        <h2 className="section-title mb-4">Add New User</h2>
        <form onSubmit={handleCreateUser} className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Username</label>
            <input
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              required
              className="input"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Password</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
              className="input"
            />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="btn-primary"
          >
            {creating ? 'Creating...' : 'Create User'}
          </button>
        </form>
      </div>

      {/* Change my password */}
      <div className="card p-6">
        <h2 className="section-title mb-4">Change My Password</h2>
        <form onSubmit={handleChangePassword} className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Current Password</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="input"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">New Password</label>
            <input
              type="password"
              value={nextPassword}
              onChange={(e) => setNextPassword(e.target.value)}
              required
              minLength={8}
              className="input"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Confirm New Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
              className="input"
            />
          </div>
          <button
            type="submit"
            disabled={changingPw}
            className="btn-primary"
          >
            {changingPw ? 'Changing...' : 'Change Password'}
          </button>
        </form>
      </div>

      {/* MFA / Two-Factor Authentication */}
      <div className="card p-6">
        <h2 className="section-title mb-4">Two-Factor Authentication (MFA)</h2>

        {mfaEnabled && !mfaSetupData && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-profit" />
              <span className="text-sm text-profit font-medium">MFA is enabled</span>
            </div>
            <p className="text-xs text-gray-500">Your account is protected with TOTP authentication.</p>
            <button
              onClick={async () => {
                setMfaLoading(true)
                try {
                  const res = await apiFetch('/api/auth/mfa/disable', { method: 'POST' })
                  if (res.ok) {
                    setMfaEnabled(false)
                    setMessage({ type: 'success', text: 'MFA disabled' })
                  }
                } catch { /* */ }
                setMfaLoading(false)
              }}
              disabled={mfaLoading}
              className="text-sm bg-loss/20 text-loss hover:bg-loss/30 px-4 py-2 rounded-lg transition-colors"
            >
              Disable MFA
            </button>
          </div>
        )}

        {!mfaEnabled && !mfaSetupData && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-gray-600" />
              <span className="text-sm text-gray-400">MFA is not enabled</span>
            </div>
            <p className="text-xs text-gray-500">Protect your account with a TOTP authenticator app (Google Authenticator, Authy, etc.)</p>
            <button
              onClick={async () => {
                setMfaLoading(true)
                try {
                  const res = await apiFetch('/api/auth/mfa/setup', { method: 'POST' })
                  if (res.ok) {
                    const data = await res.json()
                    setMfaSetupData(data)
                  }
                } catch { /* */ }
                setMfaLoading(false)
              }}
              disabled={mfaLoading}
              className="btn-primary"
            >
              Enable MFA
            </button>
          </div>
        )}

        {mfaSetupData && (
          <div className="space-y-4">
            <p className="text-sm text-gray-300">Scan this QR code with your authenticator app:</p>
            <div className="flex justify-center">
              <img src={mfaSetupData.qr_code} alt="TOTP QR Code" className="rounded-lg" style={{ width: 200, height: 200 }} />
            </div>
            <div className="text-center">
              <p className="text-xs text-gray-500 mb-1">Or enter this key manually:</p>
              <code className="text-sm text-accent bg-bg-primary px-3 py-1 rounded font-mono select-all">{mfaSetupData.secret}</code>
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Enter the 6-digit code from your app to confirm:</label>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="input max-w-[160px] text-center text-lg tracking-[0.3em] font-mono"
                  placeholder="000000"
                  maxLength={6}
                  autoComplete="one-time-code"
                />
                <button
                  onClick={async () => {
                    if (mfaCode.length !== 6) return
                    setMfaLoading(true)
                    try {
                      const res = await apiFetch('/api/auth/mfa/confirm', {
                        method: 'POST',
                        body: JSON.stringify({ secret: mfaSetupData.secret, totp_code: mfaCode }),
                      })
                      if (res.ok) {
                        setMfaEnabled(true)
                        setMfaSetupData(null)
                        setMfaCode('')
                        setMessage({ type: 'success', text: 'MFA enabled successfully!' })
                      } else {
                        const err = await res.json()
                        setMessage({ type: 'error', text: err.detail || 'Invalid code' })
                      }
                    } catch { /* */ }
                    setMfaLoading(false)
                  }}
                  disabled={mfaLoading || mfaCode.length !== 6}
                  className="btn-primary disabled:opacity-50"
                >
                  Confirm
                </button>
              </div>
            </div>
            <button
              className="text-xs text-gray-500 hover:text-gray-300"
              onClick={() => { setMfaSetupData(null); setMfaCode('') }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
