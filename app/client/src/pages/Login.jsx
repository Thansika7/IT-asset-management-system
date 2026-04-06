import React, { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { FullPageLoader } from '@/components/AppShell'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const { login, user, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from?.pathname || '/'

  useEffect(() => {
    if (!loading && user) {
      navigate(from, { replace: true })
    }
  }, [user, loading, navigate, from])

  if (loading) {
    return <FullPageLoader />
  }

  if (user) {
    return null
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(err.message || 'Invalid credentials.')
    } finally {
      setBusy(false)
    }
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
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300 mb-4">Asset Workspace</p>
            <h1 className="text-4xl font-bold tracking-tight mb-4 leading-tight">IT asset management</h1>
            <p className="text-slate-300 text-base leading-relaxed max-w-md">
              Track inventory, approvals, and assignments with a workspace tailored to each role from employees to support and finance.
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur-xl p-8 sm:p-10 shadow-2xl motion-fade-up motion-delay-1 surface-sheen">
          <div className="mb-8">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-400 mb-2">Sign in</p>
            <h2 className="text-2xl font-bold text-white">Welcome back</h2>
            <p className="text-slate-400 text-sm mt-2">Use your work email and password.</p>
          </div>

          {error ? (
            <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200 motion-fade-in">
              {error}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="motion-fade-up motion-delay-1">
              <label className="block text-xs font-semibold text-slate-400 mb-1.5" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500/40 focus:border-teal-500/50 transition-all duration-200"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="motion-fade-up motion-delay-2">
              <label className="block text-xs font-semibold text-slate-400 mb-1.5" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-500/40 focus:border-teal-500/50 transition-all duration-200"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-gradient-to-r from-teal-500 to-cyan-600 py-3 text-sm font-semibold text-white shadow-lg shadow-teal-500/25 hover:opacity-95 hover:-translate-y-0.5 disabled:opacity-60 transition-all duration-200 motion-fade-up motion-delay-3"
            >
              {busy ? 'Signing in...' : 'Continue'}
            </button>
          </form>

          <div className="mt-6 text-center motion-fade-up motion-delay-4">
            <button
              type="button"
              onClick={() => navigate('/forgot-password')}
              className="text-sm text-teal-400 hover:text-teal-300 transition-colors duration-200"
            >
              Forgot your password?
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
