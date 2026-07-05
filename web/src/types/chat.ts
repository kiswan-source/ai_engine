/**
 * Native SSE event vocabulary emitted by `core/chat/engine.py` via
 * `POST /api/v1/chat/stream` (api/routes/chat.py — protected foundation,
 * MASTER_INSTRUCTION.md Bab 45.1). This is a distinct, older vocabulary from
 * the canonical Workflow/Agent events in `types/event.ts` — chat.py predates
 * the orchestrator and is not migrated onto EVENT_CATALOG.md.
 */
export type ChatStreamEvent =
  | { type: 'session'; session_id: string }
  | { type: 'token'; text: string }
  | { type: 'tool_start'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; ok: boolean; summary: string }
  | { type: 'file'; filename: string; ftype: string; size: number }
  | { type: 'error'; message: string }
  | { type: 'done' }

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  files?: Array<{ filename: string; ftype: string; size: number }>
  pending?: boolean
}

/** GET /api/v1/chat/sessions item shape (`ChatEngine.list_sessions`). */
export interface ChatSessionSummary {
  id: string
  title: string
  message_count: number
  files: string[]
}

/** GET /api/v1/chat/sessions/{id} history item shape (`Session.history`). */
export interface ChatHistoryItem {
  type: 'user' | 'assistant'
  content: string
  [key: string]: unknown
}
