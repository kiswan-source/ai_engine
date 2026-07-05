/** Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — navigation delegated via `onOpen`. */
import { FolderKanban } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { ProjectSummary } from '@/types/project'

export function ProjectCard({ project, onOpen }: { project: ProjectSummary; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-lg border border-border p-3 text-left hover:bg-accent"
    >
      <FolderKanban size={18} className="shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{project.name}</p>
        {project.description && (
          <p className="truncate text-xs text-muted-foreground">{project.description}</p>
        )}
      </div>
      {project.status === 'archived' && (
        <Badge variant="outline" className="shrink-0 text-muted-foreground">
          Diarsipkan
        </Badge>
      )}
    </button>
  )
}
