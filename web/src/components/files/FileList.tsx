/**
 * Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — renders a flat file
 * list, download is delegated via `onDownload`.
 *
 * Tahap 25: was a plain `<a href={hrefFor(filename)} download>` — switched
 * to a button that calls back into the page, because the backend route
 * now requires `X-API-Key` (once `API_KEYS` is configured) and a bare
 * anchor click can't attach a custom header. The page owns the actual
 * fetch+blob+trigger-download logic (`fileService.downloadReport`) and any
 * error notification — this component stays a plain callback.
 */
import { File as FileIcon, Download } from 'lucide-react'
import { formatBytes } from '@/lib/utils'

interface FileListProps {
  files: Array<{ filename: string; size: number }>
  emptyLabel: string
  onDownload?: (filename: string) => void
}

export function FileList({ files, emptyLabel, onDownload }: FileListProps) {
  if (files.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyLabel}</p>
  }

  return (
    <div className="flex flex-col gap-2">
      {files.map((f) => (
        <div
          key={f.filename}
          className="flex items-center gap-3 rounded-lg border border-border p-3"
        >
          <FileIcon size={18} className="shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{f.filename}</p>
            <p className="text-xs text-muted-foreground">{formatBytes(f.size)}</p>
          </div>
          {onDownload && (
            <button
              type="button"
              onClick={() => onDownload(f.filename)}
              className="shrink-0 text-muted-foreground hover:text-foreground"
              aria-label={`Unduh ${f.filename}`}
            >
              <Download size={16} />
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
