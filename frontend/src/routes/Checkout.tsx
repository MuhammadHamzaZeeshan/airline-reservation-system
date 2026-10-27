import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api, money } from '../api/client'
import CountdownTimer from '../components/CountdownTimer'
import { useBooking } from '../store/booking'
import { useUi } from '../store/ui'

export default function Checkout() {
  const { hold, flight, idemKey, clear } = useBooking()
  const toast = useUi((s) => s.toast)
  const nav = useNavigate()
  const [names, setNames] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expired, setExpired] = useState(false)
  if (!hold || !flight) return <Navigate to="/" replace />

  async function confirm() {
    setBusy(true); setError(null)
    try {
      // NEVER optimistic: we only show the confirmation after the server answers 201.
      const r = await api('/v1/bookings', { method: 'POST', headers: { 'Idempotency-Key': idemKey! },
        body: { flight_id: hold!.flight_id, hold_id: hold!.hold_id, passengers: hold!.seats.map((s) => ({ seat_no: s, name: names[s]?.trim() || '' })) } })
      clear()
      nav(`/confirmation/${r.pnr}`, { state: { booking: r, flight } })
    } catch (e: any) {
      if (e.code === 'HOLD_EXPIRED') { setExpired(true); setError('Your hold expired. Please choose your seats again.') }
      else if (e.code === 'SEAT_CONFLICT' || e.code === 'SEAT_UNAVAILABLE') { setError(`${e.message}. Someone else was faster - please pick other seats.`); toast('error', 'Seat no longer available') }
      else setError(e.message)
    } finally { setBusy(false) }
  }
  const ready = hold.seats.every((s) => (names[s] ?? '').trim().length > 0)
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="card flex items-center justify-between p-4">
        <div><div className="font-semibold">{flight.flight_no}: {flight.origin_code} to {flight.dest_code}</div><div className="text-sm text-slate-500">Seats {hold.seats.join(', ')}</div></div>
        <div className="text-right"><div className="text-xs text-slate-500">Hold expires in</div><CountdownTimer expiresAt={hold.expires_at} onExpire={() => setExpired(true)} /></div>
      </div>
      {hold.degraded && <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Reservation holds are temporarily unavailable. Your seats are guaranteed only when you confirm.</div>}
      <div className="card space-y-3 p-4">
        <h2 className="font-semibold">Passengers</h2>
        {hold.seats.map((s) => (
          <label key={s} className="block text-sm">Passenger for seat {s}
            <input className="input mt-1" value={names[s] ?? ''} onChange={(e) => setNames({ ...names, [s]: e.target.value })} placeholder="Full name as on passport" maxLength={100} />
          </label>
        ))}
        <div className="flex justify-between border-t pt-3 font-semibold"><span>Total</span><span>{money(hold.total_price)}</span></div>
        {error && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-danger">{error}</div>}
        {expired
          ? <button className="btn-primary w-full" onClick={() => { clear(); nav(`/flight/${hold.flight_id}`) }}>Choose seats again</button>
          : <button className="btn-primary w-full" disabled={busy || !ready} onClick={confirm}>{busy ? <><span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />Confirming...</> : 'Confirm booking'}</button>}
        {!expired && <button className="btn-ghost w-full" onClick={async () => { try { await api(`/v1/holds/${hold.hold_id}`, { method: 'DELETE' }) } catch { /* expired */ } clear(); nav('/') }}>Release seats</button>}
      </div>
    </div>
  )
}
