const API_BASE = '/api'

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

  const res = await fetch(`${API_BASE}${path.startsWith('/') ? path : `/${path}`}`, {
    ...options,
    headers,
  })

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
    const msg =
      data && typeof data === 'object'
        ? data.message || data.detail || JSON.stringify(data)
        : data || res.statusText
    const err = new Error(typeof msg === 'string' ? msg : 'Request failed')
    err.status = res.status
    err.data = data
    throw err
  }

  return data
}
