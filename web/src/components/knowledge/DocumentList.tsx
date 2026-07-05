/** Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — delete delegated via `onDelete`. */
import { BookOpen, Trash2 } from 'lucide-react'
import type { KnowledgeDocument } from '@/types/knowledge'

interface DocumentListProps {
  documents: KnowledgeDocument[]
  onDelete: (id: string) => void
}

export function DocumentList({ documents, onDelete }: DocumentListProps) {
  if (documents.length === 0) {
    return <p className="text-sm text-muted-foreground">Belum ada sumber pengetahuan.</p>
  }

  return (
    <div className="flex flex-col gap-2">
      {documents.map((doc) => (
        <div key={doc.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
          <BookOpen size={18} className="shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{doc.title}</p>
            <p className="text-xs text-muted-foreground">{doc.word_count ?? 0} kata</p>
          </div>
          <button
            type="button"
            onClick={() => onDelete(doc.id)}
            aria-label={`Hapus ${doc.title}`}
            className="shrink-0 text-muted-foreground hover:text-destructive"
          >
            <Trash2 size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}
