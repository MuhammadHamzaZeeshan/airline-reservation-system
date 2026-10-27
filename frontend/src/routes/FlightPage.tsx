import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, dmy, hhmm, money } from '../api/client'
import SeatMap from '../components/SeatMap'
import { useHold } from '../hooks/useHold'
import { FlightLite } from '../store/booking'
import { useAuth } from '../store/auth'

export default function FlightPage() {
  const { id } = useParams()
  const fid = Number(id)
  const st = useLocation().state as { flight?: any } | null
  const [flight, setFlight] = useState<FlightLite | null>(st?.flight ?? null)
  const [avail, setAvail] = useState<any>(null)
  const [sel, setSel] = useState<string[]>([])
  const token = useAuth((s) => s.token)
  const nav = useNavigate()
  const { hold, busy, error } = useHold()

  useEffect(() => {
    api(`/v1/flights/${fid}/availability`).then(setAvail).catch(() => undefined)
    if (!flight) api(`/v1/flights/${fid}`).then((f) => setFlight({ ...f, origin_code: String(f.origin_id), dest_code: String(f.dest_id) })).catch(() => undefined)
  }, [fid])  // eslint-disable-line react-hooks/exhaustive-deps

  const total = sel.length * (flight?.price ?? 0)

  async function go() {
    if (!token) { nav('/login'); return }
    if (flight && (await hold(flight, sel))) nav('/checkout')
  }
  return (
    <div className="grid gap-6 md:grid-cols-[1fr_340px]">
      <div>
        <Link to="/" className="text-sm text-primary">&larr; Back to results</Link>
        <h1 className="mb-3 mt-2 text-xl font-semibold">{flight ? `${flight.flight_no} ${flight.origin_code} to ${flight.dest_code}` : 'Flight'} {flight && <span className="text-sm font-normal text-slate-500">{dmy(flight.departure_ts)} {hhmm(flight.departure_ts)}</span>}</h1>
        <SeatMap flightId={fid} selected={sel} onToggle={setSel} />
      </div>
      <aside className="card h-fit space-y-3 p-4 md:sticky md:top-20">
        <h2 className="font-semibold">Your selection</h2>
        {avail && <ul className="space-y-1 text-sm">{avail.classes.map((c: any) => (
          <li key={c.fare_class} className="flex justify-between"><span>{c.fare_class}</span>
            <span className={c.available <= 5 ? 'font-medium text-accent' : ''}>{c.available} left - {money(c.price)}</span></li>))}</ul>}
        <hr />
        {sel.length === 0 ? <p className="text-sm text-slate-500">Choose up to 9 seats on the map.</p> : (
          <ul className="text-sm">{sel.map((s) => <li key={s} className="flex justify-between"><span>Seat {s}</span><button className="text-danger" onClick={() => setSel(sel.filter((x) => x !== s))} aria-label={`Remove seat ${s}`}>remove</button></li>)}</ul>
        )}
        {sel.length > 0 && <div className="flex justify-between font-semibold"><span>Estimated total</span><span>{money(sel.length ? total : 0)}+</span></div>}
        <p className="text-xs text-slate-500">Final price depends on cabin; premium and business seats cost more. You will see the exact total after holding.</p>
        {error && <div role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-danger">{error}</div>}
        <button className="btn-primary w-full" disabled={sel.length === 0 || busy} onClick={go}>{busy ? 'Holding...' : `Hold seats (10 min)`}</button>
      </aside>
    </div>
  )
}
