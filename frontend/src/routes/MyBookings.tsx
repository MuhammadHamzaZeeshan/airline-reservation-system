import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api, dmy, hhmm, money } from '../api/client'
import { useAuth } from '../store/auth'
import { useUi } from '../store/ui'

export default function MyBookings() {
  const token = useAuth((s) => s.token)
  const toast = useUi((s) => s.toast)
  const [items, setItems] = useState<any[] | null>(null)
  const [confirm, setConfirm] = useState<any | null>(null)
  const load = () => api('/v1/bookings').then((r) => setItems(r.items)).catch((e) => toast('error', e.message))
  useEffect(() => { if (token) load() }, [token])  // eslint-disable-line react-hooks/exhaustive-deps
  if (!token) return <Navigate to="/login" replace />
  async function cancel(b: any) {
    try { await api(`/v1/bookings/${b.flight_id}/${b.pnr}`, { method: 'DELETE' }); toast('success', `Booking ${b.pnr} cancelled`); setConfirm(null); load() }
    catch (e: any) { toast('error', e.message) }
  }
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">My bookings</h1>
      {!items ? <div className="skeleton h-32" /> : items.length === 0 ? <div className="card p-8 text-center text-slate-500">You have no bookings yet.</div> : (
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="p-3">PNR</th><th>Flight</th><th>Departure</th><th>Seats</th><th>Total</th><th>Status</th><th /></tr></thead>
            <tbody>{items.map((b) => (
              <tr key={`${b.flight_id}-${b.pnr}`} className="border-t">
                <td className="p-3 font-mono font-semibold">{b.pnr}</td><td>{b.flight_no} {b.origin}-{b.dest}</td><td>{dmy(b.departure_ts)} {hhmm(b.departure_ts)}</td>
                <td>{b.tickets.map((t: any) => t.seat_no).join(', ')}</td><td>{money(b.total_price)}</td>
                <td><span className={`chip ${b.status === 'CONFIRMED' ? 'bg-green-100 text-green-800' : 'bg-slate-200 text-slate-600'}`}>{b.status.toLowerCase()}</span></td>
                <td className="pr-3 text-right">{b.status === 'CONFIRMED' && <button className="btn-ghost" onClick={() => setConfirm(b)}>Cancel</button>}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      {confirm && (
        <div role="dialog" aria-modal="true" aria-label="Confirm cancellation" className="fixed inset-0 z-30 grid place-items-center bg-black/40 p-4">
          <div className="card w-full max-w-sm space-y-3 p-5">
            <h2 className="font-semibold">Cancel booking {confirm.pnr}?</h2>
            <p className="text-sm text-slate-600">Your seats will be released immediately. This cannot be undone.</p>
            <div className="flex justify-end gap-2"><button className="btn-ghost" onClick={() => setConfirm(null)}>Keep booking</button><button className="btn-danger" onClick={() => cancel(confirm)}>Cancel booking</button></div>
          </div>
        </div>
      )}
    </div>
  )
}
