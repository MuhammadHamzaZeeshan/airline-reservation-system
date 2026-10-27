import { create } from 'zustand'

type Toast = { id: number; kind: 'error' | 'success' | 'info'; text: string }
type Ui = { rateLimited: boolean; toasts: Toast[]; setRateLimited: (v: boolean) => void; toast: (kind: Toast['kind'], text: string) => void; dismiss: (id: number) => void }
let n = 0

export const useUi = create<Ui>((set, get) => ({
  rateLimited: false, toasts: [],
  setRateLimited: (rateLimited) => set({ rateLimited }),
  toast: (kind, text) => { const id = ++n; set({ toasts: [...get().toasts, { id, kind, text }] }); setTimeout(() => get().dismiss(id), 5000) },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}))
