import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { normalizeRole } from '@/lib/roles'

const AuthContext = createContext(null)

function parseUserFromToken(token) {
  const payload = JSON.parse(atob(token.split('.')[1]))
  return {
    email: payload.sub,
    role: normalizeRole(payload.role),
    employeeId: payload.emp_id || null,
    branch: payload.branch || null,
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
    try {
      setUser(parseUserFromToken(token))
    } catch {
      logout()
    } finally {
      setLoading(false)
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
