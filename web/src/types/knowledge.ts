/** Real shapes returned by `api/routes/knowledge.py`. */
export interface KnowledgeDocument {
  id: string
  title: string
  word_count: number | null
  created_at: string
}

export interface KnowledgeHit {
  entry_id: string
  text: string
  score: number
  metadata: Record<string, unknown>
}
