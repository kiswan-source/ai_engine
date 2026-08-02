/**
 * Fase 13 (Workspace Manager UI — sidebar tree, context menu, drag & drop).
 *
 * The `GET /{workspace_id}/tree` endpoint returns one flat `files: string[]`
 * (relative paths) per registered WorkspaceFolder — there is no nested
 * directory structure server-side (see `api/routes/workspace.py::workspace_tree`
 * and `FilesystemAdapter.list_tree()`), so this component builds the nested
 * tree client-side. An empty subfolder therefore never appears (nothing in
 * the flat file list implies it) — a disclosed limitation, not a bug, same
 * class as `/tree`'s own docstring already accepts.
 *
 * Rename/Move/Copy work on files AND folders (the backend's `_move_or_copy` /
 * `FilesystemAdapter.move`/`copy` already support directories — Fase 8's own
 * chat-tool docstring says "satu file/folder"). Delete is file-only (the
 * server 400s on a directory — Workspace Slice 2's own scope), so the
 * context menu simply doesn't offer it for directory nodes rather than
 * offering an action guaranteed to fail.
 *
 * Cross-folder moves are NOT supported — `_move_or_copy` takes a single
 * `folder_id` for both source and destination, so drag-and-drop (and the
 * Move dialog) are confined to within one registered WorkspaceFolder. This
 * mirrors a real backend constraint, not a frontend simplification.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, File, Folder, FolderTree, Loader2 } from 'lucide-react'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/services/apiClient'
import { workspaceService } from '@/services/workspaceService'
import { useNotificationStore } from '@/stores/notificationStore'
import type { DeleteRequestResult, WorkspaceTreeFolder } from '@/types/workspace'

interface TreeNode {
  name: string
  fullPath: string
  isDir: boolean
  children: TreeNode[]
}

function buildTree(paths: string[]): TreeNode[] {
  const root: TreeNode = { name: '', fullPath: '', isDir: true, children: [] }
  for (const path of paths) {
    const parts = path.split('/').filter(Boolean)
    let node = root
    let acc = ''
    parts.forEach((part, i) => {
      acc = acc ? `${acc}/${part}` : part
      const isLeaf = i === parts.length - 1
      let child = node.children.find((c) => c.name === part)
      if (!child) {
        child = { name: part, fullPath: acc, isDir: !isLeaf, children: [] }
        node.children.push(child)
      } else if (!isLeaf) {
        child.isDir = true
      }
      node = child
    })
  }
  const sortRec = (n: TreeNode) => {
    n.children.sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1))
    n.children.forEach(sortRec)
  }
  sortRec(root)
  return root.children
}

function dirname(path: string): string {
  const i = path.lastIndexOf('/')
  return i === -1 ? '' : path.slice(0, i)
}

function basename(path: string): string {
  const i = path.lastIndexOf('/')
  return i === -1 ? path : path.slice(i + 1)
}

function joinPath(dir: string, name: string): string {
  return dir ? `${dir}/${name}` : name
}

/** Drag payload — JSON-encoded onto the native HTML5 DataTransfer. */
interface DragPayload {
  folderId: string
  relativePath: string
}

const DRAG_MIME = 'application/x-workspace-file'

export function WorkspaceFileTree({ workspaceId }: { workspaceId: string }) {
  const pushNotification = useNotificationStore((s) => s.push)
  const [folders, setFolders] = useState<WorkspaceTreeFolder[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [pendingDelete, setPendingDelete] = useState<{
    folderId: string
    relativePath: string
    request: DeleteRequestResult
  } | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await workspaceService.tree(workspaceId)
      setFolders(res.folders)
    } catch (e) {
      pushNotification({
        variant: 'destructive',
        message: e instanceof Error ? e.message : 'Gagal memuat daftar file Workspace',
      })
    } finally {
      setLoading(false)
    }
    // pushNotification is a stable Zustand action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId])

  useEffect(() => {
    load()
  }, [load])

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  async function withOverwriteRetry(
    action: (overwrite: boolean) => Promise<unknown>,
    confirmLabel: string,
  ) {
    try {
      await action(false)
      return true
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      if (e instanceof ApiError && message.includes('sudah ada')) {
        if (window.confirm(`${confirmLabel}\n\n${message}\n\nTimpa yang sudah ada?`)) {
          try {
            await action(true)
            return true
          } catch (e2) {
            pushNotification({ variant: 'destructive', message: e2 instanceof Error ? e2.message : String(e2) })
            return false
          }
        }
        return false
      }
      pushNotification({ variant: 'destructive', message })
      return false
    }
  }

  async function onRename(folderId: string, node: TreeNode) {
    const newName = window.prompt('Nama baru:', node.name)
    if (!newName || newName === node.name) return
    const dst = joinPath(dirname(node.fullPath), newName)
    const ok = await withOverwriteRetry(
      (overwrite) => workspaceService.moveFile(workspaceId, folderId, node.fullPath, dst, overwrite),
      `Ganti nama "${node.name}" menjadi "${newName}"?`,
    )
    if (ok) {
      pushNotification({ variant: 'success', message: `"${node.name}" diganti nama menjadi "${newName}".` })
      await load()
    }
  }

  async function onMove(folderId: string, node: TreeNode) {
    const dst = window.prompt(`Pindahkan "${node.fullPath}" ke path baru (relatif terhadap folder Workspace ini):`, node.fullPath)
    if (!dst || dst === node.fullPath) return
    const ok = await withOverwriteRetry(
      (overwrite) => workspaceService.moveFile(workspaceId, folderId, node.fullPath, dst, overwrite),
      `Pindahkan "${node.fullPath}" ke "${dst}"?`,
    )
    if (ok) {
      pushNotification({ variant: 'success', message: `Dipindahkan ke "${dst}".` })
      await load()
    }
  }

  async function onCopy(folderId: string, node: TreeNode) {
    const dst = window.prompt(`Salin "${node.fullPath}" ke path baru (relatif terhadap folder Workspace ini):`, node.fullPath)
    if (!dst || dst === node.fullPath) return
    const ok = await withOverwriteRetry(
      (overwrite) => workspaceService.copyFile(workspaceId, folderId, node.fullPath, dst, overwrite),
      `Salin "${node.fullPath}" ke "${dst}"?`,
    )
    if (ok) {
      pushNotification({ variant: 'success', message: `Disalin ke "${dst}".` })
      await load()
    }
  }

  async function onDeleteRequest(folderId: string, node: TreeNode) {
    try {
      const req = await workspaceService.deleteRequest(workspaceId, folderId, node.fullPath)
      setPendingDelete({ folderId, relativePath: node.fullPath, request: req })
    } catch (e) {
      pushNotification({ variant: 'destructive', message: e instanceof Error ? e.message : String(e) })
    }
  }

  async function onDeleteConfirm() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await workspaceService.deleteConfirm(workspaceId, pendingDelete.folderId, pendingDelete.request.token)
      pushNotification({ variant: 'success', message: `"${pendingDelete.relativePath}" dihapus.` })
      setPendingDelete(null)
      await load()
    } catch (e) {
      pushNotification({ variant: 'destructive', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setDeleting(false)
    }
  }

  function onDragStart(e: React.DragEvent, folderId: string, node: TreeNode) {
    const payload: DragPayload = { folderId, relativePath: node.fullPath }
    e.dataTransfer.setData(DRAG_MIME, JSON.stringify(payload))
    e.dataTransfer.effectAllowed = 'move'
  }

  function onDropOnDir(e: React.DragEvent, folderId: string, targetNode: TreeNode | null) {
    e.preventDefault()
    e.stopPropagation()
    const raw = e.dataTransfer.getData(DRAG_MIME)
    if (!raw) return
    let payload: DragPayload
    try {
      payload = JSON.parse(raw)
    } catch {
      return
    }
    // Backend `_move_or_copy` takes one folder_id for both src and dst —
    // moving between different registered WorkspaceFolders isn't supported.
    if (payload.folderId !== folderId) {
      pushNotification({
        variant: 'warning',
        message: 'Tidak bisa memindahkan file antar folder Workspace yang berbeda.',
      })
      return
    }
    const targetDir = targetNode ? targetNode.fullPath : ''
    const name = basename(payload.relativePath)
    const dst = joinPath(targetDir, name)
    if (dst === payload.relativePath) return
    withOverwriteRetry(
      (overwrite) => workspaceService.moveFile(workspaceId, folderId, payload.relativePath, dst, overwrite),
      `Pindahkan "${payload.relativePath}" ke "${targetDir || '(root)'}"?`,
    ).then((ok) => {
      if (ok) {
        pushNotification({ variant: 'success', message: `Dipindahkan ke "${dst}".` })
        load()
      }
    })
  }

  if (loading) {
    return (
      <div className="flex flex-col gap-1.5">
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-5/6" />
        <Skeleton className="h-6 w-4/6" />
      </div>
    )
  }

  const localFolders = folders.filter((f) => f.source_type === 'Local')

  if (localFolders.length === 0) {
    return <p className="text-sm text-muted-foreground">Belum ada folder yang terhubung.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      {localFolders.map((folder) => (
        <FolderRoot
          key={folder.id}
          folder={folder}
          expanded={expanded}
          onToggle={toggle}
          onDragStart={onDragStart}
          onDropOnDir={onDropOnDir}
          onRename={onRename}
          onMove={onMove}
          onCopy={onCopy}
          onDeleteRequest={onDeleteRequest}
        />
      ))}

      <Dialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Hapus file?</DialogTitle>
            <DialogDescription>
              {pendingDelete && (
                <>
                  <span className="font-mono text-xs">{pendingDelete.relativePath}</span>
                  {' '}({pendingDelete.request.size_bytes.toLocaleString()} bytes) akan dihapus. File ini tersimpan
                  sebagai versi sebelumnya dan dapat dipulihkan lewat riwayat versi Workspace.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDelete(null)} disabled={deleting}>
              Batal
            </Button>
            <Button variant="destructive" onClick={onDeleteConfirm} disabled={deleting}>
              {deleting && <Loader2 size={14} className="mr-1.5 animate-spin" />}
              Konfirmasi Hapus
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function FolderRoot({
  folder,
  expanded,
  onToggle,
  onDragStart,
  onDropOnDir,
  onRename,
  onMove,
  onCopy,
  onDeleteRequest,
}: {
  folder: WorkspaceTreeFolder
  expanded: Set<string>
  onToggle: (key: string) => void
  onDragStart: (e: React.DragEvent, folderId: string, node: TreeNode) => void
  onDropOnDir: (e: React.DragEvent, folderId: string, targetNode: TreeNode | null) => void
  onRename: (folderId: string, node: TreeNode) => void
  onMove: (folderId: string, node: TreeNode) => void
  onCopy: (folderId: string, node: TreeNode) => void
  onDeleteRequest: (folderId: string, node: TreeNode) => void
}) {
  // The registered WorkspaceFolder header itself is always shown expanded —
  // usually one or two roots are connected at a time, so a top-level
  // collapse toggle adds a click for no real benefit. Only nested
  // directories (TreeRow, below) are individually collapsible.
  const tree = useMemo(() => buildTree(folder.files), [folder.files])

  return (
    <div>
      <div
        className="flex items-center gap-1.5 rounded px-1.5 py-1 text-sm font-medium"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => onDropOnDir(e, folder.id, null)}
      >
        <FolderTree size={14} className="text-muted-foreground" />
        <span className="truncate">{folder.alias ?? folder.path}</span>
      </div>
      <div>
        {tree.length === 0 ? (
          <p className="pl-6 text-xs text-muted-foreground">Folder kosong.</p>
        ) : (
          tree.map((node) => (
            <TreeRow
              key={node.fullPath}
              folderId={folder.id}
              node={node}
              depth={1}
              expanded={expanded}
              onToggle={onToggle}
              onDragStart={onDragStart}
              onDropOnDir={onDropOnDir}
              onRename={onRename}
              onMove={onMove}
              onCopy={onCopy}
              onDeleteRequest={onDeleteRequest}
            />
          ))
        )}
      </div>
    </div>
  )
}

function TreeRow({
  folderId,
  node,
  depth,
  expanded,
  onToggle,
  onDragStart,
  onDropOnDir,
  onRename,
  onMove,
  onCopy,
  onDeleteRequest,
}: {
  folderId: string
  node: TreeNode
  depth: number
  expanded: Set<string>
  onToggle: (key: string) => void
  onDragStart: (e: React.DragEvent, folderId: string, node: TreeNode) => void
  onDropOnDir: (e: React.DragEvent, folderId: string, targetNode: TreeNode | null) => void
  onRename: (folderId: string, node: TreeNode) => void
  onMove: (folderId: string, node: TreeNode) => void
  onCopy: (folderId: string, node: TreeNode) => void
  onDeleteRequest: (folderId: string, node: TreeNode) => void
}) {
  const key = `${folderId}::${node.fullPath}`
  const isExpanded = expanded.has(key)

  return (
    <>
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <div
            className="flex items-center gap-1.5 rounded px-1.5 py-1 text-sm hover:bg-accent"
            style={{ paddingLeft: depth * 16 }}
            draggable
            onDragStart={(e) => onDragStart(e, folderId, node)}
            onDragOver={node.isDir ? (e) => e.preventDefault() : undefined}
            onDrop={node.isDir ? (e) => onDropOnDir(e, folderId, node) : undefined}
            onClick={() => node.isDir && onToggle(key)}
            role="button"
          >
            {node.isDir ? (
              isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
            ) : (
              <span className="inline-block w-3.5" />
            )}
            {node.isDir ? (
              <Folder size={14} className="text-muted-foreground" />
            ) : (
              <File size={14} className="text-muted-foreground" />
            )}
            <span className="truncate">{node.name}</span>
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent>
          <ContextMenuItem onSelect={() => onRename(folderId, node)}>Rename</ContextMenuItem>
          <ContextMenuItem onSelect={() => onMove(folderId, node)}>Move</ContextMenuItem>
          <ContextMenuItem onSelect={() => onCopy(folderId, node)}>Copy</ContextMenuItem>
          {!node.isDir && (
            <>
              <ContextMenuSeparator />
              <ContextMenuItem variant="destructive" onSelect={() => onDeleteRequest(folderId, node)}>
                Delete
              </ContextMenuItem>
            </>
          )}
        </ContextMenuContent>
      </ContextMenu>
      {node.isDir && isExpanded &&
        node.children.map((child) => (
          <TreeRow
            key={child.fullPath}
            folderId={folderId}
            node={child}
            depth={depth + 1}
            expanded={expanded}
            onToggle={onToggle}
            onDragStart={onDragStart}
            onDropOnDir={onDropOnDir}
            onRename={onRename}
            onMove={onMove}
            onCopy={onCopy}
            onDeleteRequest={onDeleteRequest}
          />
        ))}
    </>
  )
}
