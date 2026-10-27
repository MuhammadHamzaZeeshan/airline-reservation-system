import React, { useEffect, useState } from 'react'
import FlightCard from '../components/FlightCard'
import FilterSidebar, { Filters } from '../components/FilterSidebar'
import { useSearch } from '../hooks/useSearch'

const today = () => new Date().toISOString().slice(0, 10)
const plus = (d: number) => new Date(Date.now() + d * 86400000).toISOString().slice(0, 10)
const SORTS = [
  ['departure:asc', 'Departure (earliest)'],
  ['price:asc', 'Price (lowest)'],
  ['price:desc', 'Price (highest)'],
  ['duration:asc', 'Duration (shortest)'],
  ['arrival:asc', 'Arrival (earliest)'],
  ['seats:desc', 'Seats left (most)'],
  ['seats:asc', 'Seats left (fewest)'],
  ['price:asc,duration:asc', 'Price, then duration']
]

export default function Search() {
  const [q, setQ] = useState({
    origin: 'KHI',
    destination: 'LHR',
    date_from: today(),
    date_to: plus(350), // Updated from 60 to 350 days
    passengers: '1',
    fare_class: ''
  })
  const [filters, setFilters] = useState<Filters>({ max_price: '', max_stops: '', max_duration: '', fare_class: '' })
  const [sort, setSort] = useState('price:asc')
  const { state, loading, error, search, more } = useSearch()

  const run = (s = sort, f = filters) => search({
    origin: q.origin, destination: q.destination, date_from: `${q.date_from}T00:00:00Z`, date_to: `${q.date_to}T23:59:59Z`, passengers: q.passengers,
    sort: s, limit: 20, max_price: f.max_price, max_stops: f.max_stops, max_duration: f.max_duration, fare_class: f.fare_class || q.fare_class,
  })
  useEffect(() => { run() }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof typeof q) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setQ({ ...q, [k]: e.target.value })

  return (
    <div className="space-y-6">
      <form onSubmit={(e) => { e.preventDefault(); run() }} className="card grid gap-3 bg-gradient-to-r from-blue-50 to-white p-5 md:grid-cols-6">
        <label className="text-sm md:col-span-1">From<input className="input mt-1" value={q.origin} onChange={set('origin')} placeholder="City or code" required /></label>
        <label className="text-sm md:col-span-1">To<input className="input mt-1" value={q.destination} onChange={set('destination')} placeholder="City or code" required /></label>
        <label className="text-sm">Depart from<input className="input mt-1" type="date" value={q.date_from} onChange={set('date_from')} /></label>
        <label className="text-sm">Depart until<input className="input mt-1" type="date" value={q.date_to} onChange={set('date_to')} /></label>
        <label className="text-sm">Passengers<input className="input mt-1" type="number" min={1} max={9} value={q.passengers} onChange={set('passengers')} /></label>
        <div className="flex items-end"><button className="btn-primary w-full" disabled={loading}>{loading ? 'Searching...' : 'Search flights'}</button></div>
      </form>
      <div className="grid gap-6 md:grid-cols-[260px_1fr]">
        <FilterSidebar f={filters} onChange={(f) => { setFilters(f); run(sort, f) }} />
        <section aria-live="polite">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm text-slate-600">
              {state.count !== null && <>{state.capped ? '1,000+' : state.count.toLocaleString()} results in {state.tookMs} ms {state.cached && <span className="chip bg-green-100 text-green-800">cached</span>}</>}
            </div>
            <label className="text-sm">Sort by{' '}
              <select className="input ml-1 inline-block w-auto" value={sort} onChange={(e) => { setSort(e.target.value); run(e.target.value) }}>
                {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
          </div>
          {error && <div role="alert" className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-danger">{error}</div>}
          {loading && state.items.length === 0 && <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-28" />)}</div>}
          {!loading && !error && state.items.length === 0 && <div className="card p-8 text-center text-slate-500">No flights match. Try wider dates or fewer filters.</div>}
          <div className="space-y-3">{state.items.map((f) => <FlightCard key={f.flight_id} f={f} />)}</div>
          {state.next && <div className="mt-4 text-center"><button className="btn-ghost" onClick={more} disabled={loading}>{loading ? 'Loading...' : 'Load more'}</button></div>}
        </section>
      </div>
    </div>
  )
}