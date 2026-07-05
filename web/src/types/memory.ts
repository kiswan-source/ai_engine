/** Real shape returned by `api/routes/memory.py` `GET /{session_id}`. */
export interface ConversationTurn {
  role: string
  content: string
  [key: string]: unknown
}

export interface SessionMemory {
  session_id: string
  working: Record<string, unknown>
  conversation_history: ConversationTurn[]
  summary: string | null
  long_term: Record<string, unknown>
}
