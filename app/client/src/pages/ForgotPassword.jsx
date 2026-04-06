import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '@/lib/api'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setSuccess(false)

    try {
      const response = await apiFetch('/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email }),
      })
      setSuccess(true)
    } catch (err) {
      setError(err.message || 'An error occurred. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-stretch bg-slate-950 motion-fade-in">
        <div className="hidden lg:flex lg:w-[42%] relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-teal-500/30 via-slate-900 to-indigo-900" />
          <div className="absolute inset-0 opacity-50 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-cyan-400/20 via-transparent to-transparent motion-float-soft" />
          <div className="absolute -top-24 right-[-12%] h-72 w-72 rounded-full bg-cyan-300/10 blur-3xl motion-float-soft motion-delay-2" />
          <div className="absolute bottom-[-10%] left-[-8%] h-64 w-64 rounded-full bg-teal-400/10 blur-3xl motion-float-soft motion-delay-3" />
          <div className="relative z-10 flex w-full items-center px-12 py-16 text-white motion-fade-up">
            <div className="max-w-lg">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300 mb-4">Password Reset</p>
              <h1 className="text-4xl font-bold tracking-tight mb-4 leading-tight">Check your email</h1>
              <p className="text-slate-300 text-base leading-relaxed max-w-md">
                We've sent you a new password. Please check your personal email and use it to sign in.
              </p>
            </div>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center p-6 sm:p-10">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur-xl p-8 sm:p-10 shadow-2xl motion-fade-up motion-delay-1 surface-sheen">
            <div className="mb-8 text-center">
              <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-white mb-2">Password sent!</h2>
              <p className="text-slate-400 text-sm">
                Check your personal email for your new password.
              </p>
            </div>

            <button
              onClick={() => navigate('/login')}
              className="w-full rounded-xl bg-gradient-to-r from-teal-500 to-cyan-600 py-3 text-sm font-semibold text-white shadow-lg shadow-teal-500/25 hover:opacity-95 hover:-translate-y-0.5 transition-all duration-200"
            >
              Back to login
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-stretch bg-slate-950 motion-fade-in">
      <div className="hidden lg:flex lg:w-[42%] relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-teal-500/30 via-slate-900 to-indigo-900" />
        <div className="absolute inset-0 opacity-50 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-cyan-400/20 via-transparent to-transparent motion-float-soft" />
        <div className="absolute -top-24 right-[-12%] h-72 w-72 rounded-full bg-cyan-300/10 blur-3xl motion-float-soft motion-delay-2" />
        <div className="absolute bottom-[-10%] left-[-8%] h-64 w-64 rounded-full bg-teal-400/10 blur-3xl motion-float-soft motion-delay-3" />
        <div className="relative z-10 flex w-full items-center px-12 py-16 text-white motion-fade-up">
          <div className="max-w-lg">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300 mb-4">Password Reset</p>
            <h1 className="text-4xl font-bold tracking-tight mb-4 leading-tight">Reset your password</h1>
            <p className="text-slate-300 text-base leading-relaxed max-w-md">
              Enter your work email address and we'll send you a link to reset your password.
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur-xl p-8 sm:p-10 shadow-2xl motion-fade-up motion-delay-1 surface-sheen">
          <div className="mb-8">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-400 mb-2">Reset password</p>
            <h2 className="text-2xl font-bold text-white">Forgot your password?</h2>
            <p className="text-slate-400 text-sm mt-2">Enter your work email address and we'll send you a new password to your personal email.</p>
          </div>

          {error ? (
            <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 motion-fade-in">
              {error}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="motion-fade-up motion-delay-1">
              <label className="block text-xs font-semibold text-slate-400 mb-1.5" htmlFor="email">
                Work email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500/40 focus:border-teal-500/50 transition-all duration-200"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-gradient-to-r from-teal-500 to-cyan-600 py-3 text-sm font-semibold text-white shadow-lg shadow-teal-500/25 hover:opacity-95 hover:-translate-y-0.5 disabled:opacity-60 transition-all duration-200 motion-fade-up motion-delay-2"
            >
              {busy ? 'Sending...' : 'Send new password'}
            </button>
          </form>

          <div className="mt-6 text-center motion-fade-up motion-delay-3">
            <button
              type="button"
              onClick={() => navigate('/login')}
              className="text-sm text-teal-400 hover:text-teal-300 transition-colors duration-200"
            >
              Back to login
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}