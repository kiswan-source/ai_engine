/** Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — per-key delete delegated via `onForget`. */
import { Trash2 } from 'lucide-react'

interface KeyValueListProps {
  entries: Record<string, unknown>
  emptyLabel: string
  onForget: (key: string) => void
}

export function KeyValueList({ entries, emptyLabel, onForget }: KeyValueListProps) {
  const keys = Object.keys(entries)
  if (keys.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyLabel}</p>
  }

  return (
    <div className="flex flex-col gap-2">
      {keys.map((key) => (
        <div
          key={key}
          className="flex items-center justify-between gap-3 rounded-lg border border-border p-3"
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">{key}</p>
            <p className="truncate text-xs text-muted-foreground">{JSON.stringify(entries[key])}</p>
          </div>
          <button
            type="button"
            onClick={() => onForget(key)}
            aria-label={`Hapus ${key}`}
            className="shrink-0 text-muted-foreground hover:text-destructive"
          >
            <Trash2 size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}
