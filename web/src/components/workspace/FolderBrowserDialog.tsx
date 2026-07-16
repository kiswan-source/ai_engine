/**
 * In-app folder browser (Fase 9, DCF v5 mandate "Workspace Manager UI —
 * Native Windows Folder Connection"). Owner decision (Gate 1): no browser
 * API can hand JavaScript a real OS path — not the File System Access API,
 * not <input webkitdirectory> — that's a deliberate browser security
 * boundary, not a gap here. This is the chosen practical substitute for a
 * literal native picker: a click-to-navigate tree backed by
 * `GET /api/v1/workspace/browse-fs`, which actually gives the backend a
 * real, usable path. The user never types a path.
 */
import { useEffect, useState } from 'react'
import { Folder, ChevronRight, Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { workspaceService } from '@/services/workspaceService'
import type { BrowseFsResult } from '@/types/workspace'

export interface FolderBrowserDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (path: string, friendlyPath: string) => void
}

export function FolderBrowserDialog({ open, onOpenChange, onSelect }: FolderBrowserDialogProps) {
  const [result, setResult] = useState<BrowseFsResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async (path?: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await workspaceService.browseFs(path)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Gagal membuka folder')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      setResult(null)
      load()
    }
    // load is stable enough for this dialog's lifecycle; re-running only on open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Pilih Folder</DialogTitle>
          <DialogDescription>
            Jelajahi dan pilih folder yang ingin dihubungkan sebagai Workspace.
          </DialogDescription>
        </DialogHeader>

        {result?.friendly_path && (
          <div className="truncate rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs">
            {result.friendly_path}
          </div>
        )}

        <div className="flex h-72 flex-col overflow-y-auto rounded-md border border-border">
          {loading ? (
            <div className="flex flex-1 items-center justify-center text-muted-foreground">
              <Loader2 size={18} className="animate-spin" />
            </div>
          ) : error ? (
            <p className="p-4 text-sm text-destructive">{error}</p>
          ) : (
            <>
              {result?.parent !== null && result?.path && (
                <button
                  type="button"
                  onClick={() => load(result.parent ?? undefined)}
                  className="flex items-center gap-2 border-b border-border px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent"
                >
                  .. (naik satu tingkat)
                </button>
              )}
              {result?.entries.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">Tidak ada subfolder di sini.</p>
              ) : (
                result?.entries.map((entry) => (
                  <button
                    key={entry.path}
                    type="button"
                    onClick={() => load(entry.path)}
                    className="flex items-center gap-2 border-b border-border px-3 py-2 text-left text-sm last:border-b-0 hover:bg-accent"
                  >
                    <Folder size={15} className="shrink-0 text-muted-foreground" />
                    <span className="flex-1 truncate">{entry.name}</span>
                    <ChevronRight size={14} className="shrink-0 text-muted-foreground" />
                  </button>
                ))
              )}
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Batal
          </Button>
          <Button
            disabled={!result?.path}
            onClick={() => {
              if (result?.path) {
                onSelect(result.path, result.friendly_path ?? result.path)
                onOpenChange(false)
              }
            }}
          >
            Pilih Folder Ini
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
