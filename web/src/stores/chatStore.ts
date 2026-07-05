/** Chat State (IMPLEMENTATION_BLUEPRINT.md §7) — content of the active conversation. */
import { create } from 'zustand'
import type { ChatMessage } from '@/types/chat'

interface ChatState {
  messages: ChatMessage[]
  isStreaming: boolean
  addMessage: (message: ChatMessage) => void
  appendToLastAssistant: (text: string) => void
  setStreaming: (streaming: boolean) => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isStreaming: false,
  addMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  appendToLastAssistant: (text) =>
    set((s) => {
      const messages = [...s.messages]
      const last = messages[messages.length - 1]
      if (last && last.role === 'assistant') {
        messages[messages.length - 1] = { ...last, content: last.content + text, pending: false }
      }
      return { messages }
    }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  reset: () => set({ messages: [], isStreaming: false }),
}))
