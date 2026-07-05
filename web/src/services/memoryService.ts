/** Talks to `api/routes/memory.py` — `/api/v1/memory/*`. */
import { apiClient } from './apiClient'
import type { SessionMemory } from '@/types/memory'

export const memoryService = {
  getSessionMemory: (sessionId: string) =>
    apiClient.get<SessionMemory>(`/api/v1/memory/${encodeURIComponent(sessionId)}`),
  forgetWorking: (sessionId: string, key: string) =>
    apiClient.delete<{ deleted: boolean }>(
      `/api/v1/memory/${encodeURIComponent(sessionId)}/working/${encodeURIComponent(key)}`,
    ),
  forgetLongTerm: (sessionId: string, key: string) =>
    apiClient.delete<{ deleted: boolean }>(
      `/api/v1/memory/${encodeURIComponent(sessionId)}/long-term/${encodeURIComponent(key)}`,
    ),
  clearConversation: (sessionId: string) =>
    apiClient.delete<{ cleared: boolean }>(
      `/api/v1/memory/${encodeURIComponent(sessionId)}/conversation`,
    ),
  clearSummary: (sessionId: string) =>
    apiClient.delete<{ cleared: boolean }>(
      `/api/v1/memory/${encodeURIComponent(sessionId)}/summary`,
    ),
}
