import { Fragment, useEffect, useRef, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, money } from '../api/client'
import StatCard from '../components/StatCard'
import { useAuth } from '../store/auth'

const SIMS: [string, string, string][] = [['load-test', 'Run load test', 'btn-primary'], ['heavy-load', 'Heavy load (5,000 users)', 'btn-primary'], ['race-test', 'Run race test', 'btn-primary'],
  ['kill-api', 'Kill API node', 'btn-danger'], ['kill-worker', 'Kill DB worker', 'btn-danger'], ['restore-all', 'Restore all', 'btn-ghost']]

function Dot({ s }: { s: string }) { return <i className={`mr-2 inline-block h-2.5 w-2.5 rounded-full ${s === 'up' ? 'bg-success' : s === 'disabled' ? 'bg-slate-300' : 'bg-danger'}`} aria-label={s} /> }

export default function Admin() {
  const { isAdmin, token } = useAuth()
  const [dash, setDash] = useState<any>(null)
  const [cluster, setCluster] = useState<any>(null)
  const [log, setLog] = useState<string[]>([])
  const [job, setJob] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const timer = useRef<number>()
  const refresh = () => {
    api('/v1/admin/dashboard').then(setDash).catch((e) => setErr(e.message))
    api('/v1/admin/cluster').then(setCluster).catch((e) => setErr(e.message))
  }
  useEffect(() => { if (isAdmin) { refresh(); const t = setInterval(refresh, 10000); return () => clearInterval(t) } }, [isAdmin])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => clearInterval(timer.current), [])
  if (!token || !isAdmin) return <Navigate to="/login" replace />

  async function run(name: string) {
    setLog([`> starting ${name}...`]); setErr(null)
    try {
      const r = await api(`/v1/admin/simulate/${name}`, { method: 'POST' }); setJob(r.job_id)
      clearInterval(timer.current)
      timer.current = window.setInterval(async () => {
        const l = await api(`/v1/admin/simulate/${r.job_id}/log`).catch(() => null)
        if (l) { setLog(l.lines); if (l.status !== 'running') { clearInterval(timer.current); refresh() } }
      }, 1500)
    } catch (e: any) { setLog([`error: ${e.message}`]) }
  }
  const k = dash?.kpi ?? {}
  const grid: Record<string, number> = {}; let max = 1
  dash?.hours?.forEach((h: any) => { grid[`${h.dow}-${h.hour}`] = Number(h.bookings); max = Math.max(max, Number(h.bookings)) })
  const days = (dash?.bookings_per_day ?? []).map((d: any) => ({ day: d.day.slice(5), bookings: Number(d.bookings), revenue: Math.round(Number(d.revenue)) }))
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Admin dashboard</h1>
      {err && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-danger">{err}</div>}
      {dash?.degraded && <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Analytics store (ClickHouse) is unreachable - showing partial data. Booking and search are unaffected.</div>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Bookings today" value={Number(k.bookings_today ?? 0).toLocaleString()} />
        <StatCard label="Revenue today" value={money(Number(k.revenue_today ?? 0))} />
        <StatCard label="Load factor (next 2 h)" value={dash?.load_factor != null ? `${dash.load_factor}%` : 'n/a'} />
        <StatCard label="Error rate (1 min)" value={dash?.error_rate != null ? `${dash.error_rate}%` : 'n/a'} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card p-4"><h2 className="mb-2 text-sm font-semibold">Bookings per day (30 d)</h2><ResponsiveContainer width="100%" height={220}><LineChart data={days}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Line type="monotone" dataKey="bookings" stroke="#1D4ED8" dot={false} /></LineChart></ResponsiveContainer></div>
        <div className="card p-4"><h2 className="mb-2 text-sm font-semibold">Revenue per day</h2><ResponsiveContainer width="100%" height={220}><AreaChart data={days}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Area type="monotone" dataKey="revenue" stroke="#16A34A" fill="#BBF7D0" /></AreaChart></ResponsiveContainer></div>
        <div className="card p-4"><h2 className="mb-2 text-sm font-semibold">Top routes</h2><ResponsiveContainer width="100%" height={240}><BarChart data={dash?.top_routes ?? []} layout="vertical"><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" fontSize={11} /><YAxis type="category" dataKey="route" width={80} fontSize={11} /><Tooltip /><Bar dataKey="bookings" fill="#1D4ED8" /></BarChart></ResponsiveContainer></div>
        <div className="card p-4"><h2 className="mb-2 text-sm font-semibold">Peak hours (day of week x hour)</h2>
          <div className="overflow-x-auto"><div className="grid gap-px" style={{ gridTemplateColumns: 'auto repeat(24, minmax(10px, 1fr))' }}>
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, i) => (<Fragment key={d}>
              <span className="pr-2 text-xs text-slate-500">{d}</span>
              {Array.from({ length: 24 }, (_, h) => { const v = grid[`${i + 1}-${h}`] ?? 0; return <span key={`${d}${h}`} title={`${d} ${h}:00 - ${v}`} className="h-5 rounded-sm" style={{ background: `rgba(29,78,216,${0.08 + 0.92 * (v / max)})` }} /> })}
            </Fragment>))}
          </div></div></div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card space-y-3 p-4">
          <h2 className="text-sm font-semibold">Cluster</h2>
          <div className="grid grid-cols-2 gap-1 text-sm">{Object.entries(cluster?.services ?? {}).map(([n, s]) => <div key={n}><Dot s={String(s)} />{n}</div>)}</div>
          {cluster?.citus ? (<>
            <table className="w-full text-left text-sm"><thead className="text-xs uppercase text-slate-500"><tr><th>Worker</th><th>Shards</th><th>Rows (est.)</th><th>Size</th></tr></thead>
              <tbody>{cluster.shards.map((s: any) => <tr key={s.node} className="border-t"><td>{s.node}</td><td>{s.shards}</td><td>{s.est_rows.toLocaleString()}</td><td>{(s.size_bytes / 1e6).toFixed(0)} MB</td></tr>)}</tbody></table>
            <div className="text-sm">Replication lag: {Object.keys(cluster.replication_lag_s).length === 0 ? 'no replicas attached (lite stack)' : Object.entries(cluster.replication_lag_s).map(([n, v]) => `node ${n}: ${Number(v).toFixed(2)} s`).join(', ')}</div>
          </>) : <div className="text-sm text-slate-500">Not a Citus cluster.</div>}
        </div>
        <div className="card space-y-3 p-4">
          <h2 className="text-sm font-semibold">Simulation panel</h2>
          <div className="flex flex-wrap gap-2">{SIMS.map(([n, l, c]) => <button key={n} className={c} onClick={() => run(n)}>{l}</button>)}</div>
          <pre className="h-56 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-green-300" aria-live="polite">{log.join('\n') || 'Output appears here.'}</pre>
          {job && <div className="text-xs text-slate-400">job {job}. Watch Grafana at :3000 while it runs.</div>}
        </div>
      </div>
    </div>
  )
}
