import { useState } from 'react'
import { api } from '../api/client'
import { FlightLite, Hold, useBooking } from '../store/booking'

export function useHold() {
  const setHold = useBooking((s) => s.setHold)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function hold(flight: FlightLite, seats: string[]): Promise<boolean> {
    setBusy(true); setError(null)
    try {
      const h = await api<Hold>('/v1/holds', { method: 'POST', body: { flight_id: flight.flight_id, seats } })
      setHold(h, flight)
      return true
    } catch (e: any) { setError(e.code === 'SEAT_CONFLICT' || e.code === 'SEAT_UNAVAILABLE' ? `${e.message}. Pick another seat.` : e.message); return false }
    finally { setBusy(false) }
  }
  return { hold, busy, error }
}
