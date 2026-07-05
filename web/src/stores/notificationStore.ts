/** Notification State (IMPLEMENTATION_BLUEPRINT.md §7) — toasts + persistent connection/approval alerts. */
import { create } from 'zustand'

export interface AppNotification {
  id: string
  variant: 'success' | 'warning' | 'destructive' | 'info'
  message: string
  createdAt: number
}

interface NotificationState {
  items: AppNotification[]
  push: (n: Omit<AppNotification, 'id' | 'createdAt'>) => void
  dismiss: (id: string) => void
}

export const useNotificationStore = create<NotificationState>((set) => ({
  items: [],
  push: (n) =>
    set((s) => ({
      items: [...s.items, { ...n, id: crypto.randomUUID(), createdAt: Date.now() }],
    })),
  dismiss: (id) => set((s) => ({ items: s.items.filter((n) => n.id !== id) })),
}))
