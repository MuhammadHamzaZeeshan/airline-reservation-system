import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, dur, hhmm, money, dmy } from '../api/client'
import { Flight } from '../hooks/useSearch'

const CLS: Record<string, string> = { ECONOMY: 'Economy', PREMIUM: 'Premium', BUSINESS: 'Business' }

export default function FlightCard({ f }: { f: Flight }) {
  const [similar, setSimilar] = useState<any[] | null>(null)
  const [busy, setBusy] = useState(false)
  async function showSimilar() {
    setBusy(true)
    try { setSimilar((await api(`/v1/flights/${f.flight_id}/similar`)).items) } finally { setBusy(false) }
  }
  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex w-36 items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-full bg-slate-100 text-xs font-bold text-slate-500" aria-hidden>{f.flight_no.slice(0, 2)}</div>
          <div><div className="text-sm font-semibold">{f.flight_no}</div><div className="max-w-[6rem] truncate text-xs text-slate-500">{f.airline_name}</div></div>
        </div>
        <div className="flex flex-1 items-center gap-4 min-w-[260px]">
          <div className="text-center"><div className="text-lg font-semibold">{hhmm(f.departure_ts)}</div><div className="text-xs text-slate-500">{f.origin_code}</div></div>
          <div className="flex-1 text-center text-xs text-slate-500">
            <div>{dur(f.duration_min)}</div>
            <div className="my-1 h-px bg-slate-300" />
            <div>{f.stops === 0 ? 'Non-stop' : `${f.stops} stop${f.stops > 1 ? 's' : ''}`}</div>
          </div>
          <div className="text-center"><div className="text-lg font-semibold">{hhmm(f.arrival_ts)}</div><div className="text-xs text-slate-500">{f.dest_code}</div></div>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-500">{dmy(f.departure_ts)}</div>
          <div className="text-xl font-semibold">{money(f.price)}</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          {f.classes.map((c) => (
            <span key={c.fare_class} className={`chip ${c.available === 0 ? 'bg-slate-100 text-slate-400' : c.available <= 5 ? 'bg-amber-100 text-amber-800' : 'bg-blue-50 text-blue-700'}`}>
              {CLS[c.fare_class]}: {c.available === 0 ? 'sold out' : c.available <= 5 ? `only ${c.available} left` : `${c.available} seats`}
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={showSimilar} disabled={busy}>{busy ? '...' : 'Similar'}</button>
          <Link className="btn-primary" to={`/flight/${f.flight_id}`} state={{ flight: f }}>Select</Link>
        </div>
      </div>
      {similar && (
        <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
          <div className="mb-1 font-medium">Similar flights (vector search)</div>
          {similar.length === 0 && <div className="text-slate-500">No similar flights found.</div>}
          {similar.map((s) => (
            <div key={s.flight_id} className="flex justify-between border-t border-slate-200 py-1">
              <span>{s.flight_no} {hhmm(s.departure_ts)} {dmy(s.departure_ts)} - {dur(s.duration_min)}, {s.stops} stop(s)</span>
              <span className="font-medium">{money(s.price)}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  )
}
