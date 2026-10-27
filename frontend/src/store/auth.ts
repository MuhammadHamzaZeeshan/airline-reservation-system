import { create } from 'zustand'

type Auth = { token: string | null; username: string | null; isAdmin: boolean; set: (t: string, u: string, a: boolean) => void; logout: () => void }
const saved = JSON.parse(localStorage.getItem('ars-auth') ?? 'null')

export const useAuth = create<Auth>((set) => ({
  token: saved?.token ?? null, username: saved?.username ?? null, isAdmin: saved?.isAdmin ?? false,
  set: (token, username, isAdmin) => { localStorage.setItem('ars-auth', JSON.stringify({ token, username, isAdmin })); set({ token, username, isAdmin }) },
  logout: () => { localStorage.removeItem('ars-auth'); set({ token: null, username: null, isAdmin: false }) },
}))
