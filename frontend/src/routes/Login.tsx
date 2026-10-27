import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../store/auth'
import { useDebounce } from '../hooks/useDebounce'

export default function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [f, setF] = useState({ username: '', email: '', password: '', full_name: '' })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [avail, setAvail] = useState<'idle' | 'checking' | 'available' | 'taken' | 'invalid'>('idle')
  const setAuth = useAuth((s) => s.set)
  const nav = useNavigate()
  const uname = useDebounce(f.username.trim(), 300)  // live check, debounced 300 ms

  useEffect(() => {
    if (mode !== 'register' || uname.length < 3) { setAvail('idle'); return }
    let live = true
    setAvail('checking')
    api(`/v1/users/availability?username=${encodeURIComponent(uname)}`).then((r) => {
      if (!live) return
      setAvail(!r.username.valid ? 'invalid' : r.username.available ? 'available' : 'taken')
    }).catch(() => live && setAvail('idle'))
    return () => { live = false }
  }, [uname, mode])

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      const r = mode === 'login'
        ? await api('/v1/auth/login', { method: 'POST', body: { username: f.username, password: f.password } })
        : await api('/v1/auth/register', { method: 'POST', body: { username: f.username, email: f.email, password: f.password, full_name: f.full_name } })
      setAuth(r.access_token, r.username, !!r.is_admin)
      nav('/')
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const badge = { idle: '', checking: 'checking...', available: 'available', taken: 'already taken', invalid: '3-32 chars: a-z, A-Z, 0-9, _ or .' }[avail]
  return (
    <div className="mx-auto grid max-w-4xl overflow-hidden rounded-card border border-slate-200 bg-white shadow-card lg:grid-cols-[0.85fr_1.15fr]">
      <div className="auth-intro hidden p-9 text-center lg:flex lg:flex-col lg:items-center lg:justify-center">
        <div className="max-w-xs">
          <span className="eyebrow">ARS flights</span>
          <h1 className="mt-5 text-3xl font-semibold tracking-tight text-slate-950">Travel plans, kept simple.</h1>
          <p className="mt-4 text-sm leading-6 text-slate-600">Find the right flight, keep an eye on your booking, and get where you are going with less fuss.</p>
        </div>
      </div>
      <form onSubmit={submit} className="space-y-5 p-6 sm:p-9">
        <div className="mb-7">
          <p className="eyebrow lg:hidden">ARS flights</p>
          <h2 className="text-2xl font-semibold tracking-tight text-slate-950">{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
          <p className="mt-1 text-sm text-slate-500">{mode === 'login' ? 'Sign in to manage your trips.' : 'Save your details for a smoother booking experience.'}</p>
        </div>
        <div className="flex rounded-lg bg-slate-100 p-1">
          {(['login', 'register'] as const).map((m) => (
            <button type="button" key={m} onClick={() => { setMode(m); setErr(null) }} className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition ${mode === m ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>{m === 'login' ? 'Log in' : 'Register'}</button>
          ))}
        </div>
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">Demo access</p>
          <p className="mt-1 text-sm text-slate-700">
            User <code>Hamza</code> / <code>hamza1234</code>
          </p>
          <p className="mt-0.5 text-sm text-slate-700">
            Admin <code>Admin_Hamza</code> / <code>admin1234</code>
          </p>
        </div>
        <label className="field-label">Username{mode === 'login' ? ' or email' : ''}
          <input className="input mt-1" value={f.username} onChange={set('username')} required autoComplete="username" />
          {mode === 'register' && badge && <span className={`text-xs ${avail === 'available' ? 'text-success' : avail === 'checking' ? 'text-slate-400' : 'text-danger'}`}>{badge}</span>}
        </label>
        {mode === 'register' && <>
          <label className="field-label">Email<input className="input mt-1" type="email" value={f.email} onChange={set('email')} required autoComplete="email" /></label>
          <label className="field-label">Full name <span className="font-normal text-slate-400">(optional)</span><input className="input mt-1" value={f.full_name} onChange={set('full_name')} autoComplete="name" /></label>
        </>}
        <label className="field-label">Password<input className="input mt-1" type="password" minLength={mode === 'register' ? 8 : 1} value={f.password} onChange={set('password')} required autoComplete={mode === 'login' ? 'current-password' : 'new-password'} /></label>
        {err && <div role="alert" className="rounded-lg border border-red-100 bg-red-50 p-3 text-sm text-danger">{err}</div>}
        <button className="btn-primary w-full" disabled={busy || (mode === 'register' && (avail === 'taken' || avail === 'invalid'))}>{busy ? 'Please wait...' : mode === 'login' ? 'Log in' : 'Create account'}</button>
      </form>
    </div>
  )
}
