import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

export type Seat = { seat_no: string; fare_class: string; status: 'available' | 'held' | 'booked' }
type SeatMapData = { seats: Seat[]; letters: string[]; classes: { fare_class: string; price: number | null }[] }

const COLOR: Record<string, string> = { available: 'bg-seat-available hover:ring-2 hover:ring-primary', selected: 'bg-seat-selected text-white', held: 'bg-seat-held', booked: 'bg-seat-booked' }

export default function SeatMap({ flightId, selected, onToggle, max = 9 }: { flightId: number; selected: string[]; onToggle: (s: string[]) => void; max?: number }) {
  const [map, setMap] = useState<SeatMapData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    const load = () => api<SeatMapData>(`/v1/flights/${flightId}/seatmap`).then((m) => live && setMap(m)).catch((e) => live && setErr(e.message))
    load(); const t = setInterval(load, 15000)  // other buyers hold/book seats: refresh periodically
    return () => { live = false; clearInterval(t) }
  }, [flightId])

  const rows = useMemo(() => {
    const r: Record<number, Seat[]> = {}
    map?.seats.forEach((s) => { (r[parseInt(s.seat_no)] ??= []).push(s) })
    return Object.entries(r).map(([n, seats]) => ({ n: Number(n), seats, cls: seats[0].fare_class }))
  }, [map])

  if (err) return <div className="card p-4 text-danger">Could not load the seat map: {err}</div>
  if (!map) return <div className="skeleton h-96 w-full" />
  const price = (c: string) => map.classes.find((x) => x.fare_class === c)?.price
  let last = ''
  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap gap-4 text-xs" aria-hidden>
        {[['available', 'Available'], ['selected', 'Selected'], ['held', 'Held by someone'], ['booked', 'Booked']].map(([k, l]) => (
          <span key={k} className="flex items-center gap-1"><i className={`inline-block h-4 w-4 rounded ${COLOR[k].split(' ')[0]}`} />{l}</span>
        ))}
      </div>
      <div className="mx-auto w-fit rounded-t-[60px] border border-slate-300 bg-slate-50 px-6 pb-4 pt-8" role="group" aria-label="Aircraft seat map">
        {rows.map((r) => {
          const header = r.cls !== last ? (last = r.cls, true) : false
          return (
            <div key={r.n}>
              {header && <div className="my-2 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">{r.cls}{price(r.cls) != null ? ` - $${price(r.cls)}` : ''}</div>}
              <div className="mb-1 flex items-center justify-center gap-1">
                <span className="w-6 text-right text-xs text-slate-400">{r.n}</span>
                {r.seats.map((s, i) => {
                  const isSel = selected.includes(s.seat_no)
                  const disabled = s.status !== 'available' && !isSel
                  const state = isSel ? 'selected' : s.status
                  return (
                    <span key={s.seat_no} className={i === 3 ? 'ml-5' : ''}>
                      <button type="button" disabled={disabled} aria-pressed={isSel}
                        aria-label={`Seat ${s.seat_no}, ${s.fare_class.toLowerCase()}, ${isSel ? 'selected' : s.status}`}
                        className={`h-8 w-8 rounded text-xs font-medium transition focus:outline-none focus:ring-2 focus:ring-primary ${COLOR[state]} ${disabled ? 'cursor-not-allowed' : ''}`}
                        onClick={() => onToggle(isSel ? selected.filter((x) => x !== s.seat_no) : selected.length < max ? [...selected, s.seat_no] : selected)}>
                        {s.seat_no.replace(/[0-9]/g, '')}
                      </button>
                    </span>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
