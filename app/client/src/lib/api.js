const API_BASE = '/api'

/**
 * Turn FastAPI / Pydantic error bodies into a single readable string.
 * - App handlers: { error, message }
 * - HTTPException: { detail: string }
 * - Validation 422: { detail: [{ loc, msg, type }, ...] }
 */
export function formatApiErrorBody(data) {
  if (data == null) return null
  if (typeof data === 'string') return data
  if (typeof data !== 'object') return String(data)

  if (typeof data.message === 'string' && data.message) {
    return data.error ? `${data.error}: ${data.message}` : data.message
  }

  const d = data.detail
  if (typeof d === 'string' && d) return d
  if (Array.isArray(d)) {
    return d
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object') {
          const loc = Array.isArray(item.loc) ? item.loc.filter((x) => x !== 'body').join('.') : ''
          const msg = item.msg || item.message || ''
          return loc ? `${loc}: ${msg}` : msg || JSON.stringify(item)
        }
        return String(item)
      })
      .filter(Boolean)
      .join(' ')
  }

  return data.detail != null ? JSON.stringify(data.detail) : JSON.stringify(data)
}

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('access_token')
  const headers = {
    ...options.headers,
  }
  if (options.body && !headers['Content-Type'] && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json'
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let res
  try {
    res = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, {
      ...options,
      headers,
    })
  } catch (e) {
    const err = new Error(e?.message || 'Network error — is the API running and reachable?')
    err.status = 0
    err.cause = e
    throw err
  }

  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) {
    const msg = formatApiErrorBody(data) || res.statusText || 'Request failed'
    const err = new Error(msg)
    err.status = res.status
    err.data = data
    throw err
  }

  return data
}
