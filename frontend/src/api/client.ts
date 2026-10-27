import { useAuth } from '../store/auth'
import { useUi } from '../store/ui'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) { super(message); this.status = status; this.code = code }
}

/** fetch wrapper: adds the JWT, parses the {error,message,request_id} body, retries ONCE on 429 after Retry-After (and shows a banner). */
export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; headers?: Record<string, string>; retry?: boolean } = {}): Promise<T> {
  const token = useAuth.getState().token
  const headers: Record<string, string> = { ...(opts.body ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...opts.headers }
  const res = await fetch(path, { method: opts.method ?? 'GET', headers, body: opts.body ? JSON.stringify(opts.body) : undefined })
  if (res.status === 429 && opts.retry !== false) {
    useUi.getState().setRateLimited(true)
    await new Promise((r) => setTimeout(r, (Number(res.headers.get('Retry-After')) || 1) * 1000))
    useUi.getState().setRateLimited(false)
    return api<T>(path, { ...opts, retry: false })
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    if (res.status === 401 && token) useAuth.getState().logout()
    throw new ApiError(res.status, data?.error ?? 'ERROR', data?.message ?? res.statusText)
  }
  return data as T
}

export const qs = (o: Record<string, unknown>) =>
  Object.entries(o).filter(([, v]) => v !== '' && v !== undefined && v !== null).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&')

export const money = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
export const hhmm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
export const dmy = (iso: string) => new Date(iso).toLocaleDateString([], { day: '2-digit', month: 'short', year: 'numeric' })
export const dur = (m: number) => `${Math.floor(m / 60)}h ${m % 60}m`
