import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { useUi } from '../store/ui'
import { api } from '../api/client'

export default function Layout() {
  const { token, username, isAdmin, logout } = useAuth()
  const { rateLimited, toasts, dismiss } = useUi()
  const nav = useNavigate()
  const link = ({ isActive }: { isActive: boolean }) => `nav-link ${isActive ? 'nav-link-active' : ''}`
  return (
    <div className="flex min-h-screen flex-col">
      <nav className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1200px] flex-wrap items-center gap-1 px-4 py-3 sm:px-6">
          <Link to="/" className="brand mr-3" aria-label="ARS flights home">
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M21 3.5 3.8 10.2a1 1 0 0 0 .02 1.88l6.3 2.35 2.35 6.3a1 1 0 0 0 1.88.02L21 3.5Z" fill="currentColor" />
                <path d="m10.2 14.45 4.35-4.35" stroke="#1D4ED8" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </span>
            <span>ARS <span className="font-normal text-slate-400">flights</span></span>
          </Link>
          <div className="flex items-center gap-1">
            <NavLink to="/" end className={link}>Search</NavLink>
            <NavLink to="/bookings" className={link}>My Bookings</NavLink>
            <NavLink to="/network" className={link}>Network</NavLink>
          </div>
          {isAdmin && <NavLink to="/admin" className={link}>Admin</NavLink>}
          <div className="ml-auto flex items-center gap-3 text-sm">
            {token ? (<>
              <span className="hidden text-slate-500 sm:inline">Hi, <strong className="font-medium text-slate-700">{username}</strong></span>
              <button className="btn-ghost" onClick={async () => { try { await api('/v1/auth/logout', { method: 'POST' }) } catch { /* ignore */ } logout(); nav('/login') }}>Log out</button>
            </>) : <Link className="btn-primary" to="/login">Log in</Link>}
          </div>
        </div>
      </nav>
      {rateLimited && <div role="status" className="bg-amber-100 py-2 text-center text-sm text-amber-900">The service is busy - retrying your request in a moment...</div>}
      <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-8 sm:px-6"><Outlet /></main>
      <footer className="mt-8 border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-3 px-4 py-6 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <p className="font-medium text-slate-700">ARS flights</p>
            <p className="mt-1">Simple booking, thoughtfully arranged.</p>
          </div>
          <div className="flex gap-4">
            <span>Help centre</span>
            <span>Terms</span>
            <span>Privacy</span>
          </div>
          <p className="text-xs">© {new Date().getFullYear()} ARS</p>
        </div>
      </footer>
      <div className="fixed bottom-4 right-4 z-20 space-y-2" aria-live="polite">
        {toasts.map((t) => (
          <button key={t.id} onClick={() => dismiss(t.id)} className={`block max-w-sm rounded-lg px-4 py-3 text-left text-sm text-white shadow-lg ${t.kind === 'error' ? 'bg-danger' : t.kind === 'success' ? 'bg-success' : 'bg-slate-800'}`}>{t.text}</button>
        ))}
      </div>
    </div>
  )
}
