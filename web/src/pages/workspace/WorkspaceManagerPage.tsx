/**
 * Workspace Manager (Fase 9, DCF v5 mandate "Workspace Manager UI — Native
 * Windows Folder Connection") — top-level sidebar page, NOT nested under a
 * Project. This is the "Cursor/VS Code-style" entry point the mandate asks
 * for: the user connects a local folder and everything else (Project,
 * Workspace, mount, scan) happens automatically via
 * `POST /api/v1/workspace/quick-connect` — see that route's docstring.
 * `pages/projects/WorkspacePage.tsx` (the older per-Project detail view)
 * stays untouched for existing workflows; this page is additive.
 */
import { useCallback, useEffect, useState } from 'react'
import { FolderPlus, FolderOpen, RefreshCw, AlertTriangle, Unlink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { FolderBrowserDialog } from '@/components/workspace/FolderBrowserDialog'
import { workspaceService } from '@/services/workspaceService'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { MyWorkspace, QuickConnectResult } from '@/types/workspace'

const STATUS_VARIANT: Record<string, 'default' | 'outline' | 'destructive'> = {
  Active: 'default',
  Scanning: 'outline',
  Indexing: 'outline',
  Error: 'destructive',
}

function friendlyOf(ws: MyWorkspace | QuickConnectResult): string {
  return ws.friendly_root_path ?? ws.root_path ?? ws.folders[0]?.alias ?? ws.id
}

export default function WorkspaceManagerPage() {
  const current = useWorkspaceStore((s) => s.current)
  const setCurrent = useWorkspaceStore((s) => s.setCurrent)
  const pushNotification = useNotificationStore((s) => s.push)

  const [workspaces, setWorkspaces] = useState<MyWorkspace[]>([])
  const [loading, setLoading] = useState(true)
  const [connecting, setConnecting] = useState(false)
  const [browserOpen, setBrowserOpen] = useState(false)
  // Last quick-connect's scan summary — the mandate's "114 Files" line.
  // Deliberately not re-fetched on every render (would mean re-scanning
  // every connected Workspace just to render a list): this is a Slice 1
  // simplification, refreshed whenever this Workspace is (re)connected or
  // explicitly rescanned, not continuously live.
  const [lastScan, setLastScan] = useState<QuickConnectResult['scan'] | null>(null)

  const loadMine = useCallback(async () => {
    try {
      const res = await workspaceService.mine()
      setWorkspaces(res.workspaces)
    } catch (e) {
      pushNotification({
        variant: 'destructive',
        message: e instanceof Error ? e.message : 'Gagal memuat daftar Workspace',
      })
    } finally {
      setLoading(false)
    }
    // pushNotification is a stable Zustand action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    loadMine()
  }, [loadMine])

  async function onFolderSelected(path: string, friendlyPath: string) {
    setConnecting(true)
    try {
      const ws = await workspaceService.quickConnect(path)
      setCurrent(ws)
      setLastScan(ws.scan)
      await loadMine()
      pushNotification({ variant: 'success', message: `✓ Workspace terhubung: ${friendlyPath}` })
    } catch (e) {
      pushNotification({
        variant: 'destructive',
        message: e instanceof Error ? e.message : 'Gagal menghubungkan folder',
      })
    } finally {
      setConnecting(false)
    }
  }

  async function onSwitch(ws: MyWorkspace) {
    setCurrent(ws)
    setLastScan(null)
    // Refreshing the switched-to Workspace's status doubles as the "folder
    // moved/deleted" detection (mandate's Error Handling section) — a
    // rescan that fails flips status to "Error", surfaced via the badge
    // below; a full moved-folder "Reconnect" flow (rebinding the SAME
    // Workspace id to a new path) is a later slice — for now, reconnecting
    // means Add Folder again, which is always available.
    try {
      const result = await workspaceService.scan(ws.id)
      setLastScan(result)
      await loadMine()
    } catch {
      // scan() already flips workspace.status to "Error" server-side;
      // loadMine() picks that up so the badge reflects it either way.
      await loadMine()
    }
  }

  async function onDisconnect(ws: MyWorkspace) {
    // Soft-delete only (api/routes/workspace.py::delete_workspace) — the
    // Workspace *registration* is removed, the real folder/files on disk
    // are never touched (ADR-0005). This is the mandate's own "memutuskan
    // koneksi Workspace" requirement, missed in the first pass of this Slice.
    const label = friendlyOf(ws)
    if (!window.confirm(`Putuskan koneksi ke "${label}"?\n\nFile di folder tersebut TIDAK akan terhapus — hanya koneksi Workspace-nya yang diputuskan.`)) {
      return
    }
    try {
      await workspaceService.remove(ws.id)
      if (current?.id === ws.id) {
        setCurrent(null)
        setLastScan(null)
      }
      await loadMine()
      pushNotification({ variant: 'success', message: `Koneksi ke "${label}" diputuskan.` })
    } catch (e) {
      pushNotification({
        variant: 'destructive',
        message: e instanceof Error ? e.message : 'Gagal memutuskan koneksi Workspace',
      })
    }
  }

  const currentWs = workspaces.find((w) => w.id === current?.id) ?? (current as MyWorkspace | null)

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Workspace</h1>
          <p className="text-sm text-muted-foreground">
            Hubungkan folder lokal — AI bekerja langsung terhadapnya, tanpa upload manual.
          </p>
        </div>
        <Button onClick={() => setBrowserOpen(true)} disabled={connecting}>
          <FolderPlus size={16} className="mr-1.5" /> Add Folder
        </Button>
      </div>

      {current && (
        <section className="rounded-lg border border-border p-4">
          <div className="mb-2 flex items-center gap-2">
            {currentWs?.status === 'Error' ? (
              <AlertTriangle size={16} className="text-destructive" />
            ) : (
              <span className="text-primary">✓</span>
            )}
            <span className="font-medium">
              {currentWs?.status === 'Error' ? 'Workspace tidak tersedia' : 'Workspace Terhubung'}
            </span>
            {currentWs && (
              <Badge variant={STATUS_VARIANT[currentWs.status] ?? 'outline'} className="ml-auto">
                {currentWs.status}
              </Badge>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-muted-foreground">Folder</div>
              <div className="truncate font-mono text-xs">{current && friendlyOf(current as MyWorkspace)}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Files</div>
              <div>
                {lastScan
                  ? lastScan.document_count + lastScan.image_count + lastScan.gis_count + lastScan.other_count
                  : '—'}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Last Indexed</div>
              <div>{currentWs?.last_scan_at ?? 'Belum pernah'}</div>
            </div>
          </div>
          {currentWs?.status === 'Error' && (
            <p className="mt-3 text-sm text-muted-foreground">
              Folder ini mungkin sudah dipindahkan atau dihapus. Klik{' '}
              <button type="button" className="underline" onClick={() => setBrowserOpen(true)}>
                Add Folder
              </button>{' '}
              untuk menghubungkan ulang.
            </p>
          )}
        </section>
      )}

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Workspace Terhubung</h2>
          <Button size="icon" variant="ghost" onClick={loadMine} aria-label="Muat ulang daftar">
            <RefreshCw size={14} />
          </Button>
        </div>
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : workspaces.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Belum ada folder terhubung. Klik "Add Folder" untuk memulai.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {workspaces.map((ws) => (
              <div
                key={ws.id}
                className={`flex items-center gap-2 rounded-lg border p-3 transition-colors ${
                  current?.id === ws.id
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:bg-accent'
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSwitch(ws)}
                  className="flex min-w-0 flex-1 items-center gap-3 text-left"
                >
                  <FolderOpen size={16} className="shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{friendlyOf(ws)}</span>
                </button>
                <Badge variant={STATUS_VARIANT[ws.status] ?? 'outline'}>{ws.status}</Badge>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={`Putuskan koneksi ${friendlyOf(ws)}`}
                  onClick={() => onDisconnect(ws)}
                >
                  <Unlink size={14} />
                </Button>
              </div>
            ))}
          </div>
        )}
      </section>

      <FolderBrowserDialog open={browserOpen} onOpenChange={setBrowserOpen} onSelect={onFolderSelected} />
    </div>
  )
}
