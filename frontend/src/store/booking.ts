import { create } from 'zustand'

export type Hold = { hold_id: string; flight_id: number; seats: string[]; expires_at: number; total_price: number; degraded: boolean }
export type FlightLite = { flight_id: number; flight_no: string; origin_code: string; dest_code: string; departure_ts: string; arrival_ts: string; price: number }
type B = { hold: Hold | null; flight: FlightLite | null; idemKey: string | null; setHold: (h: Hold, f: FlightLite) => void; clear: () => void }

// The idempotency key is created ONCE per hold, so a retry after a network error/failover returns the original booking, never a second one.
export const useBooking = create<B>((set) => ({
  hold: null, flight: null, idemKey: null,
  setHold: (hold, flight) => set({ hold, flight, idemKey: crypto.randomUUID() }),
  clear: () => set({ hold: null, flight: null, idemKey: null }),
}))
