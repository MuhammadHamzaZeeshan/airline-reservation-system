import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { api } from '../api/client'

export default function Network() {
  const [g, setG] = useState<any>(null)
  const [sel, setSel] = useState<string[]>([])
  const [paths, setPaths] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(800)
  useEffect(() => { api('/v1/routes/network?limit=250').then(setG).catch((e) => setErr(e.message)) }, [])
  useEffect(() => { const f = () => setW(box.current?.clientWidth ?? 800); f(); window.addEventListener('resize', f); return () => window.removeEventListener('resize', f) }, [])
  const data = useMemo(() => g ? { nodes: g.nodes.map((n: any) => ({ ...n })), links: g.edges.map((e: any) => ({ ...e })) } : { nodes: [], links: [] }, [g])
  const highlight = new Set(paths?.shortest ?? [])

  function click(n: any) {
    const next = sel.length >= 2 ? [n.id] : [...sel, n.id]
    setSel(next); setPaths(null)
    if (next.length === 2) api(`/v1/routes/path?origin=${next[0]}&destination=${next[1]}&max_stops=2`).then(setPaths).catch((e) => setErr(e.message))
  }
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Route network</h1>
      <p className="text-sm text-slate-500">Nodes are airports, line width is flights per week. Click two airports to see connecting paths.
        {g?.source && <span className="chip ml-2 bg-slate-100 text-slate-600">source: {g.source}{g.degraded ? ' (fallback)' : ''}</span>}</p>
      {err && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-danger">{err}</div>}
      <div className="grid gap-4 md:grid-cols-[1fr_280px]">
        <div ref={box} className="card overflow-hidden">
          {g ? <ForceGraph2D width={w} height={520} graphData={data} nodeLabel={(n: any) => `${n.id} - ${n.city}`}
            linkWidth={(l: any) => Math.max(0.5, Math.min(6, Math.log2(1 + l.weekly_flights)))} linkDirectionalArrowLength={3}
            nodeColor={(n: any) => sel.includes(n.id) ? '#F59E0B' : highlight.has(n.id) ? '#16A34A' : '#1D4ED8'} onNodeClick={click}
            nodeCanvasObjectMode={() => 'after'} nodeCanvasObject={(n: any, ctx: CanvasRenderingContext2D, s: number) => { ctx.font = `${10 / s}px sans-serif`; ctx.fillStyle = '#334155'; ctx.fillText(n.id, n.x + 4, n.y + 3) }} />
            : <div className="skeleton h-[520px]" />}
        </div>
        <aside className="card space-y-2 p-4 text-sm">
          <h2 className="font-semibold">Paths</h2>
          <div>Selected: {sel.join(' to ') || 'none'}</div>
          {paths && (paths.paths.length === 0 ? <div className="text-slate-500">No route within 2 stops.</div> :
            <ol className="list-decimal space-y-1 pl-5">{paths.paths.map((p: string[], i: number) => <li key={i} className={i === 0 ? 'font-semibold' : ''}>{p.join(' > ')}{i === 0 ? ' (shortest)' : ''}</li>)}</ol>)}
        </aside>
      </div>
    </div>
  )
}
