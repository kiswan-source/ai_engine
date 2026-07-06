/**
 * Project Workspace (MASTER_INSTRUCTION.md Bab 69.14, ADR-0005, Tahap 19) —
 * sub-page of the Projects area, not a standalone sidebar item (per the
 * hand-off doc's explicit instruction and AI_WORKSPACE_ARCHITECTURE.md §8's
 * "11 fixed areas" rule). Structure mirrors `ProjectsPage.tsx`'s
 * `ProjectDetailView` (skeleton loading, notification store for errors).
 *
 * Renders exactly the Bab 69.14 field list: Workspace Path, Folder List,
 * Status, Last Scan, Document/Image/GIS Count, Vector Status, Knowledge
 * Status, Storage Used, Index Status. Document/Image/GIS Count and Storage
 * Used come from the last `POST .../scan` response (not part of the
 * Workspace GET payload) — held in local state until the next scan.
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, FolderPlus, RefreshCw, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { workspaceService } from '@/services/workspaceService'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { Workspace, WorkspaceScanResult } from '@/types/workspace'
import { ApiError } from '@/services/apiClient'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

const STATUS_VARIANT: Record<string, 'default' | 'outline' | 'destructive'> = {
  Active: 'default',
  Scanning: 'outline',
  Indexing: 'outline',
  Error: 'destructive',
}

export default function WorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const pushNotification = useNotificationStore((s) => s.push)
  const setCurrent = useWorkspaceStore((s) => s.setCurrent)

  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [loading, setLoading] = useState(true)
  const [scanResult, setScanResult] = useState<WorkspaceScanResult | null>(null)
  const [chunksIndexed, setChunksIndexed] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [mountPath, setMountPath] = useState('')
  const [mountAlias, setMountAlias] = useState('')

  // Returns null on 404 ("no Workspace yet"), rethrows anything else — the
  // useEffect below and reload() (called from mutation handlers) both
  // consume this the same way.
  const fetchWorkspace = useCallback(async (): Promise<Workspace | null> => {
    if (!projectId) return null
    try {
      return await workspaceService.getByProject(projectId)
    } catch (e) {
      if (e instanceof ApiError && e.message.toLowerCase().includes('not found')) {
        return null
      }
      throw e
    }
  }, [projectId])

  useEffect(() => {
    fetchWorkspace()
      .then((ws) => {
        setWorkspace(ws)
        setCurrent(ws)
      })
      .catch((e) => {
        pushNotification({
          variant: 'destructive',
          message: e instanceof Error ? e.message : 'Gagal memuat workspace',
        })
      })
      .finally(() => setLoading(false))
    // pushNotification/setCurrent are stable Zustand actions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchWorkspace])

  async function reload() {
    const ws = await fetchWorkspace()
    setWorkspace(ws)
    setCurrent(ws)
  }

  async function onCreate() {
    if (!projectId) return
    setBusy(true)
    try {
      const ws = await workspaceService.create(projectId)
      setWorkspace(ws)
      setCurrent(ws)
    } catch (e) {
      pushNotification({ variant: 'destructive', message: e instanceof Error ? e.message : 'Gagal membuat workspace' })
    } finally {
      setBusy(false)
    }
  }

  async function onMount() {
    if (!workspace || !mountPath.trim()) return
    setBusy(true)
    try {
      await workspaceService.mount(workspace.id, mountPath.trim(), mountAlias.trim() || undefined)
      setMountPath('')
      setMountAlias('')
      await reload()
      pushNotification({ variant: 'success', message: 'Folder terdaftar.' })
    } catch (e) {
      pushNotification({ variant: 'destructive', message: e instanceof Error ? e.message : 'Gagal mendaftarkan folder' })
    } finally {
      setBusy(false)
    }
  }

  async function onScan() {
    if (!workspace) return
    setBusy(true)
    try {
      const result = await workspaceService.scan(workspace.id)
      setScanResult(result)
      await reload()
    } catch (e) {
      pushNotification({ variant: 'destructive', message: e instanceof Error ? e.message : 'Scan gagal' })
    } finally {
      setBusy(false)
    }
  }

  async function onIndex() {
    if (!workspace) return
    setBusy(true)
    try {
      const result = await workspaceService.index(workspace.id)
      setChunksIndexed(result.chunks_indexed)
      await reload()
      pushNotification({ variant: 'success', message: `${result.chunks_indexed} bagian dokumen terindeks.` })
    } catch (e) {
      pushNotification({ variant: 'destructive', message: e instanceof Error ? e.message : 'Index gagal' })
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <Skeleton className="h-64 w-full max-w-2xl" />
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <button
        type="button"
        onClick={() => navigate(`/projects/${projectId}`)}
        className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} /> Kembali ke Proyek
      </button>

      <div>
        <h1 className="text-2xl font-semibold">Workspace</h1>
        <p className="text-sm text-muted-foreground">
          Registrasikan folder lokal sebagai sumber kerja Agent, selain unggah file satu per satu.
        </p>
      </div>

      {!workspace ? (
        <section className="flex flex-col gap-3 rounded-lg border border-border p-4">
          <p className="text-sm text-muted-foreground">Proyek ini belum punya Workspace.</p>
          <Button size="sm" className="w-fit" onClick={onCreate} disabled={busy}>
            Buat Workspace
          </Button>
        </section>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-4 rounded-lg border border-border p-4 text-sm">
            <div>
              <div className="text-muted-foreground">Status</div>
              <Badge variant={STATUS_VARIANT[workspace.status] ?? 'outline'}>{workspace.status}</Badge>
            </div>
            <div>
              <div className="text-muted-foreground">Workspace Path</div>
              <div className="truncate font-mono text-xs">{workspace.root_path ?? '—'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Last Scan</div>
              <div>{workspace.last_scan_at ?? 'Belum pernah'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Storage Used</div>
              <div>{scanResult ? formatBytes(scanResult.total_size_bytes) : '—'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Document / Image / GIS Count</div>
              <div>
                {scanResult ? `${scanResult.document_count} / ${scanResult.image_count} / ${scanResult.gis_count}` : '—'}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Index Status</div>
              <div>{chunksIndexed !== null ? `${chunksIndexed} chunk terindeks` : 'Belum diindeks'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Vector Status</div>
              <div>{chunksIndexed !== null && chunksIndexed > 0 ? 'Terisi' : 'Kosong'}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Knowledge Status</div>
              <div>{chunksIndexed !== null && chunksIndexed > 0 ? 'Tersambung ke RAG' : 'Belum tersambung'}</div>
            </div>
          </section>

          <section className="flex gap-2">
            <Button size="sm" variant="outline" onClick={onScan} disabled={busy || workspace.folders.length === 0}>
              <Search size={14} className="mr-1" /> Scan
            </Button>
            <Button size="sm" variant="outline" onClick={onIndex} disabled={busy || workspace.folders.length === 0}>
              <RefreshCw size={14} className="mr-1" /> Index ke Knowledge
            </Button>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-medium">Folder List</h2>
            {workspace.folders.length === 0 ? (
              <p className="text-sm text-muted-foreground">Belum ada folder terdaftar.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {workspace.folders.map((f) => (
                  <div key={f.id} className="flex items-center justify-between rounded-lg border border-border p-3">
                    <div>
                      <div className="text-sm font-medium">{f.alias ?? f.path}</div>
                      <div className="font-mono text-xs text-muted-foreground">{f.path}</div>
                    </div>
                    <Badge variant="outline">{f.source_type}</Badge>
                  </div>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              <input
                value={mountPath}
                onChange={(e) => setMountPath(e.target.value)}
                placeholder="Path folder lokal (mis. /data/proyek-x)"
                className="flex-1 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
              />
              <input
                value={mountAlias}
                onChange={(e) => setMountAlias(e.target.value)}
                placeholder="Alias (opsional)"
                className="w-32 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
              />
              <Button size="icon" onClick={onMount} disabled={busy || !mountPath.trim()} aria-label="Daftarkan folder">
                <FolderPlus size={16} />
              </Button>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
