/**
 * Session State (IMPLEMENTATION_BLUEPRINT.md §7) — the navigational backbone
 * (§7.2 rule 4): Conversation → Workflow → Trace → Approval → History
 * (AI_WORKSPACE_ARCHITECTURE.md §7). Any component needing "which session am
 * I in" reads this, not chatStore/workflowStore directly.
 */
import { create } from 'zustand'

interface SessionState {
  conversationId: string | null
  activeTraceId: string | null
  isResuming: boolean
  setConversationId: (id: string | null) => void
  setActiveTraceId: (id: string | null) => void
  setResuming: (resuming: boolean) => void
}

export const useSessionStore = create<SessionState>((set) => ({
  conversationId: null,
  activeTraceId: null,
  isResuming: false,
  setConversationId: (conversationId) => set({ conversationId }),
  setActiveTraceId: (activeTraceId) => set({ activeTraceId }),
  setResuming: (isResuming) => set({ isResuming }),
}))
