import { useCallback, useState } from 'react'
import { api, qs } from '../api/client'

export type ClassInfo = { fare_class: string; available: number; total: number; price: number }
export type Flight = {
  flight_id: number; flight_no: string; airline_name: string; origin_code: string; origin_city: string; dest_code: string; dest_city: string
  departure_ts: string; arrival_ts: string; duration_min: number; stops: number; price: number; seats_left: number; classes: ClassInfo[]
}
export type SearchState = { items: Flight[]; count: number | null; capped: boolean; tookMs: number | null; cached: boolean; next: string | null }

/** Cursor (keyset) pagination: `more()` sends the opaque cursor from the previous page. No OFFSET. */
export function useSearch() {
  const [state, setState] = useState<SearchState>({ items: [], count: null, capped: false, tookMs: null, cached: false, next: null })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useState<Record<string, unknown> | null>(null)

  const run = useCallback(async (p: Record<string, unknown>, append = false, cursor?: string) => {
    setLoading(true); setError(null)
    try {
      const r = await api(`/v1/flights/search?${qs({ ...p, cursor })}`)
      setState((s) => ({ items: append ? [...s.items, ...r.items] : r.items, count: append ? s.count : r.count, capped: append ? s.capped : r.count_capped,
        tookMs: r.took_ms, cached: r.cached, next: r.next_cursor }))
    } catch (e: any) { setError(e.message); if (!append) setState((s) => ({ ...s, items: [], next: null, count: 0 })) }
    finally { setLoading(false) }
  }, [])

  return {
    state, loading, error,
    search: (p: Record<string, unknown>) => { setParams(p); return run(p) },
    more: () => params && state.next ? run(params, true, state.next) : undefined,
  }
}
