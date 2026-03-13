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
    </div>
  )
}
