/**
 * History State (IMPLEMENTATION_BLUEPRINT.md §7) — filled only after a
 * Workflow/Conversation finishes (§7.3 rule 3). No dedicated History API
 * exists yet (Feature Readiness Matrix: "REQUIRES ADAPTER"); Phase 1 backs
 * this with `chatService.listSessions()` as the closest real data source.
 */
import { create } from 'zustand'
import type { ChatSessionSummary } from '@/types/chat'

interface HistoryState {
  items: ChatSessionSummary[]
  loading: boolean
  setItems: (items: ChatSessionSummary[]) => void
  setLoading: (loading: boolean) => void
}

export const useHistoryStore = create<HistoryState>((set) => ({
  items: [],
  loading: false,
  setItems: (items) => set({ items }),
  setLoading: (loading) => set({ loading }),
}))
