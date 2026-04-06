import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '@/lib/api'
import { useAuth } from '@/context/AuthContext'

export default function ChangePassword() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)

    if (newPassword !== confirmPassword) {
      setError('New password and confirmation must match.')
      return
    }

    setBusy(true)
    try {
      await apiFetch('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      setSuccess('Password updated successfully.')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setTimeout(() => navigate('/'), 1000)
    } catch (err) {
      setError(err.message || 'Unable to change password.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-6 sm:p-8 max-w-3xl mx-auto">
      <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="space-y-3 mb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-500">Security</p>
          <h1 className="text-3xl font-bold text-slate-900">Change password</h1>
          <p className="text-sm text-slate-600">Update your account password to keep your access secure.</p>
          {user?.email ? <p className="text-xs text-slate-500">Signed in as <span className="font-medium text-slate-800">{user.email}</span></p> : null}
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Current password</label>
            <input
              type="password"
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">New password</label>
              <input
                type="password"
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Confirm new password</label>
              <input
                type="password"
                className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>
          </div>

          {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}
          {success ? <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{success}</div> : null}

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="submit"
              disabled={busy}
              className="inline-flex items-center justify-center rounded-2xl bg-slate-900 text-white px-5 py-3 text-sm font-semibold disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Save new password'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="inline-flex items-center justify-center rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Back to dashboard
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
