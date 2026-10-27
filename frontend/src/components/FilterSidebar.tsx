export type Filters = { max_price: string; max_stops: string; max_duration: string; fare_class: string }

export default function FilterSidebar({ f, onChange }: { f: Filters; onChange: (f: Filters) => void }) {
  const set = (k: keyof Filters) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => onChange({ ...f, [k]: e.target.value })
  return (
    <aside className="card space-y-4 p-4" aria-label="Filters">
      <h2 className="font-semibold">Filters</h2>
      <label className="block text-sm">Max price (USD)
        <input className="input mt-1" type="number" min={0} value={f.max_price} onChange={set('max_price')} placeholder="any" />
      </label>
      <label className="block text-sm">Max duration (minutes)
        <input className="input mt-1" type="number" min={0} value={f.max_duration} onChange={set('max_duration')} placeholder="any" />
      </label>
      <label className="block text-sm">Stops
        <select className="input mt-1" value={f.max_stops} onChange={set('max_stops')}>
          <option value="">Any</option><option value="0">Non-stop only</option><option value="1">Up to 1 stop</option><option value="2">Up to 2 stops</option>
        </select>
      </label>
      <label className="block text-sm">Cabin
        <select className="input mt-1" value={f.fare_class} onChange={set('fare_class')}>
          <option value="">Any</option><option value="ECONOMY">Economy</option><option value="PREMIUM">Premium</option><option value="BUSINESS">Business</option>
        </select>
      </label>
    </aside>
  )
}
