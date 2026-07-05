/** Talks to `api/routes/knowledge.py` — `/api/v1/knowledge/*`. */
import { apiClient } from './apiClient'
import type { KnowledgeDocument, KnowledgeHit } from '@/types/knowledge'

export const knowledgeService = {
  listDocuments: () =>
    apiClient.get<{ documents: KnowledgeDocument[] }>('/api/v1/knowledge/documents'),
  ingestDocument: (title: string, text: string) =>
    apiClient.post<{ id: string; title: string; chunks_indexed: number }>(
      '/api/v1/knowledge/documents',
      {
        title,
        text,
      },
    ),
  deleteDocument: (id: string) =>
    apiClient.delete<{ deleted: boolean }>(`/api/v1/knowledge/documents/${encodeURIComponent(id)}`),
  search: (query: string) =>
    apiClient.get<{ hits: KnowledgeHit[] }>(
      `/api/v1/knowledge/search?q=${encodeURIComponent(query)}`,
    ),
}
