/**
 * Talks to the real `/api/v1/chat/*` contract (api/routes/chat.py — protected
 * foundation, MASTER_INSTRUCTION.md Bab 45.1). Its own SSE vocabulary
 * (`types/chat.ts` `ChatStreamEvent`) is parsed here, not through
 * `eventStream.ts` (that one is for the future canonical Workflow/Agent
 * events — a different, newer contract this endpoint predates).
 */
import { apiClient } from './apiClient'
import type { ChatStreamEvent, ChatSessionSummary, ChatHistoryItem } from '@/types/chat'

export interface StreamChatArgs {
  sessionId: string | null
  message: string
  model?: string
  files?: string[]
  /** Bab 69.5/Fase 8 — the Project Workspace this session should read/write
   * through, if any (`api/routes/chat.py`'s `ChatRequest.workspace_id`).
   * Omitted (undefined/null) means no Workspace: the backend behaves exactly
   * as it always has, upload-only. */
  workspaceId?: string | null
  signal?: AbortSignal
  onEvent: (event: ChatStreamEvent) => void
}

/** POST /api/v1/chat/stream — parses the `data: {...}\n\n` SSE frames from api/routes/chat.py. */
export async function streamChat({
  sessionId,
  message,
  model,
  files,
  workspaceId,
  signal,
  onEvent,
}: StreamChatArgs): Promise<void> {
  const res = await apiClient.raw('/api/v1/chat/stream', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      message,
      model,
      files: files ?? [],
      workspace_id: workspaceId ?? null,
    }),
    signal,
  })
  if (!res.ok || !res.body) {
    throw new Error(`Chat stream failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      const json = line.slice('data: '.length)
      try {
        onEvent(JSON.parse(json) as ChatStreamEvent)
      } catch {
        // Malformed frame — skip rather than crash the stream (mirrors
        // EVENT_CATALOG.md §5.3 "fail soft" principle for unknown/bad events).
      }
    }
  }
}

export const chatService = {
  streamChat,
  listSessions: () => apiClient.get<{ sessions: ChatSessionSummary[] }>('/api/v1/chat/sessions'),
  getSessionHistory: (sessionId: string) =>
    apiClient.get<{ session_id: string; history: ChatHistoryItem[] }>(
      `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`,
    ),
  deleteSession: (sessionId: string) =>
    apiClient.delete<{ deleted: boolean }>(
      `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`,
    ),
  listModels: () => apiClient.get<{ default: string; available: string[] }>('/api/v1/chat/models'),
  uploadFiles: (sessionId: string, files: File[]) => {
    const form = new FormData()
    form.set('session_id', sessionId)
    files.forEach((f) => form.append('files', f))
    return apiClient.post<{
      session_id: string
      files: Array<{ filename: string; path: string; size: number }>
    }>('/api/v1/chat/upload', form)
  },
}
