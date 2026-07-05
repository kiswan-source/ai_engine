/** Attachment State (IMPLEMENTATION_BLUEPRINT.md §7) — files uploaded/produced in the active conversation. */
import { create } from 'zustand'

export interface Attachment {
  filename: string
  ftype: string
  size: number
  direction: 'uploaded' | 'generated'
}

interface AttachmentState {
  items: Attachment[]
  add: (attachment: Attachment) => void
  reset: () => void
}

export const useAttachmentStore = create<AttachmentState>((set) => ({
  items: [],
  add: (attachment) => set((s) => ({ items: [...s.items, attachment] })),
  reset: () => set({ items: [] }),
}))
