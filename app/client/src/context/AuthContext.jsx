import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { normalizeRole } from '@/lib/roles'

const AuthContext = createContext(null)

function parseUserFromToken(token) {
  const payload = JSON.parse(atob(token.split('.')[1]))
  return {
    email: payload.sub,
    role: normalizeRole(payload.role),
    name: null,
    employeeId: payload.emp_id || null,
    branch: payload.branch || null,
    organizationId: payload.organization_id || null,
    permissions: null,
  }
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(() => Boolean(localStorage.getItem('access_token')))
  const [token, setToken] = useState(() => localStorage.getItem('access_token'))
  const navigate = useNavigate()

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    setToken(null)
    setUser(null)
    fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
    navigate('/login')
  }, [navigate])

  useEffect(() => {
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    let active = true

    const hydrateUser = async () => {
      try {
        const parsed = parseUserFromToken(token)
        if (active) setUser(parsed)

        const response = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
        })

        if (!response.ok) {
          // Only log out on 401/403, not on other errors (timeout, 5xx, etc)
          if (response.status === 401 || response.status === 403) {
            if (active) logout()
          } else {
            // For other errors, keep user logged in (might be temporary server issue)
            console.warn('Failed to load user profile:', response.status)
          }
          return
        }

        const profile = await response.json()
        if (!active) return

        setUser({
          ...parsed,
          name: profile.name || parsed.name,
          email: profile.email || parsed.email,
          role: normalizeRole(profile.role || parsed.role),
          employeeId: profile.employee_id || parsed.employeeId,
          branch: profile.branch || parsed.branch,
          organizationId: profile.organization_id || parsed.organizationId,
          permissions: profile.permissions || null,
        })
      } catch (error) {
        // Network error or other issue - keep user logged in, don't auto-logout
        console.warn('Error hydrating user:', error)
      } finally {
        if (active) setLoading(false)
      }
    }

    hydrateUser()
    return () => {
      active = false
    }
  }, [token, logout])

  const login = async (email, password) => {
    const response = await fetch('/api/auth/login/json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: email, password }),
    })

    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}))
      const msg = errBody.message || errBody.detail || 'Login failed'
      throw new Error(typeof msg === 'string' ? msg : 'Login failed')
    }

    const { access_token } = await response.json()
    localStorage.setItem('access_token', access_token)
    setToken(access_token)
    navigate('/')
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
