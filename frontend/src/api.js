// Backend API qatlami — barcha so'rovlar shu yerdan o'tadi.
// Bazaviy manzil .env dagi VITE_API_BASE dan (default localhost:8000).
const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// Nisbiy havolalarni (masalan fayl yuklab olish proksisi) to'liq manzilga aylantiradi
export const apiUrl = (path) => (path?.startsWith('/') ? BASE + path : path)

async function request(method, path, { params, body } = {}) {
  const url = new URL(BASE + path)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
    }
  }
  const opts = { method }
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' }
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(url, opts)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const b = await res.json()
      detail = b.detail || b.error || detail
    } catch { /* JSON emas */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

export const api = {
  tenders: (params) => request('GET', '/tenders', { params }),
  tender: (id) => request('GET', `/tenders/${id}`),
  stats: (params) => request('GET', '/stats', { params }),
  regions: (params) => request('GET', '/regions', { params }),
  statuses: () => request('GET', '/statuses'),
  categories: () => request('GET', '/categories'),
  freshness: () => request('GET', '/freshness'),
  // Aqlli moslashtirish
  getProfile: () => request('GET', '/profile'),
  saveProfile: (body) => request('PUT', '/profile', { body }),
  match: (body) => request('POST', '/match', { body }),
  // Saqlangan qidiruvlar (A bosqich)
  searches: () => request('GET', '/searches'),
  createSearch: (body) => request('POST', '/searches', { body }),
  updateSearch: (id, body) => request('PUT', `/searches/${id}`, { body }),
  deleteSearch: (id) => request('DELETE', `/searches/${id}`),
  // Mahsulot katalogi + katalog-asosli moslik
  catalog: () => request('GET', '/catalog'),
  createProduct: (body) => request('POST', '/catalog', { body }),
  updateProduct: (id, body) => request('PUT', `/catalog/${id}`, { body }),
  deleteProduct: (id) => request('DELETE', `/catalog/${id}`),
  catalogMatch: (body) => request('POST', '/catalog/match', { body }),
  catalogNewCount: () => request('GET', '/catalog/new-count'),
  catalogSeen: () => request('POST', '/catalog/seen'),
}
