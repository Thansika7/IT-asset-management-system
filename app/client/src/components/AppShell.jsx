import React from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

export function FullPageLoader() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950">
      <div className="h-12 w-12 rounded-full border-2 border-white/20 border-t-teal-400 animate-spin mb-4" />
      <p className="text-sm font-medium text-slate-300 tracking-wide">Loading workspace…</p>
    </div>
  )
}

export function ProtectedShell({ anyOfRoles }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <FullPageLoader />
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (anyOfRoles?.length && !anyOfRoles.includes(user.role)) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

export function RoleGate({ roles, children }) {
  const { user, loading } = useAuth()

  if (loading) {
    return <FullPageLoader />
  }

  if (!user || !roles.includes(user.role)) {
    return <Navigate to="/" replace />
  }

  return children
}
