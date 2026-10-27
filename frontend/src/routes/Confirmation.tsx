import { Link, useLocation } from 'react-router-dom'
import { dmy, hhmm, money } from '../api/client'

export default function Confirmation() {
  const st = useLocation().state as { booking?: any; flight?: any } | null
  const b = st?.booking
  if (!b) return <div className="card p-6">No booking to show. <Link className="text-primary" to="/bookings">See my bookings</Link></div>
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="card p-6 text-center">
        <div className="text-sm text-slate-500">Booking confirmed{b.idempotent_replay ? ' (already processed)' : ''}</div>
        <div className="my-2 font-mono text-4xl font-bold tracking-widest text-primary">{b.pnr}</div>
        {st?.flight && <div className="text-sm">{st.flight.flight_no}: {st.flight.origin_code} to {st.flight.dest_code}, {dmy(st.flight.departure_ts)} {hhmm(st.flight.departure_ts)}</div>}
      </div>
      <div className="card divide-y">
        {b.tickets.map((t: any) => (
          <div key={t.ticket_no} className="flex items-center justify-between p-4 text-sm">
            <div><div className="font-medium">{t.passenger_name}</div><div className="font-mono text-xs text-slate-500">ticket {t.ticket_no}</div></div>
            <div className="text-right"><div>Seat <b>{t.seat_no}</b> ({t.fare_class.toLowerCase()})</div><div>{money(t.price)}</div></div>
          </div>
        ))}
        <div className="flex justify-between p-4 font-semibold"><span>Total paid</span><span>{money(b.total_price)}</span></div>
      </div>
      <div className="no-print flex gap-2"><button className="btn-primary" onClick={() => window.print()}>Print / save as PDF</button><Link className="btn-ghost" to="/bookings">My bookings</Link></div>
    </div>
  )
}
