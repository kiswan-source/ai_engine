/** Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — renders a flat file list, download is delegated via `hrefFor`. */
import { File as FileIcon, Download } from 'lucide-react'
import { formatBytes } from '@/lib/utils'

interface FileListProps {
  files: Array<{ filename: string; size: number }>
  emptyLabel: string
  hrefFor?: (filename: string) => string
}

export function FileList({ files, emptyLabel, hrefFor }: FileListProps) {
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
          {hrefFor && (
            <a
              href={hrefFor(f.filename)}
              className="shrink-0 text-muted-foreground hover:text-foreground"
              aria-label={`Unduh ${f.filename}`}
              download
            >
              <Download size={16} />
            </a>
          )}
        </div>
      ))}
    </div>
  )
}
