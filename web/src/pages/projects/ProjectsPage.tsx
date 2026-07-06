/**
 * Projects — first backend implementation of the Phase 3 Project entity
 * (PROJECT_SPECIFICATION.md). Standalone grouping for now: not yet linked
 * to actual Conversation/File data (api/routes/projects.py module
 * docstring) — that wiring is a separate, later decision.
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, FolderKanban, Trash2, UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ProjectCard } from '@/components/projects/ProjectCard'
import { projectService } from '@/services/projectService'
import { useProjectStore } from '@/stores/projectStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { ProjectSummary, ProjectDetail } from '@/types/project'

export default function ProjectsPage() {
  const { projectId } = useParams()
  return projectId ? <ProjectDetailView projectId={projectId} /> : <ProjectListView />
}

function ProjectListView() {
  const navigate = useNavigate()
  const setActiveProjectId = useProjectStore((s) => s.setActiveProjectId)
  const pushNotification = useNotificationStore((s) => s.push)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)

  const fetchProjects = useCallback(() => projectService.list(), [])

  useEffect(() => {
    fetchProjects()
      .then((res) => setProjects(res.projects))
      .finally(() => setLoading(false))
  }, [fetchProjects])

  async function onCreate() {
    if (!name.trim()) return
    setCreating(true)
    try {
      await projectService.create(name)
      setName('')
      const res = await fetchProjects()
      setProjects(res.projects)
    } catch (e) {
      pushNotification({
        variant: 'destructive',
        message: e instanceof Error ? e.message : 'Gagal membuat proyek',
      })
    } finally {
      setCreating(false)
    }
  }

  function openProject(id: string) {
    setActiveProjectId(id)
    navigate(`/projects/${id}`)
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Projects</h1>
        <p className="text-sm text-muted-foreground">Pengelompokan pekerjaan jangka panjang.</p>
      </div>

      <section className="flex gap-2 rounded-lg border border-border p-4">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onCreate()}
          placeholder="Nama proyek baru…"
          className="flex-1 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
        />
        <Button size="sm" onClick={onCreate} disabled={creating || !name.trim()}>
          {creating ? 'Membuat…' : 'Buat'}
        </Button>
      </section>

      {loading ? (
        <Skeleton className="h-14 w-full" />
      ) : projects.length === 0 ? (
        <p className="text-sm text-muted-foreground">Belum ada proyek.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} onOpen={() => openProject(p.id)} />
          ))}
        </div>
      )}
    </div>
  )
}

function ProjectDetailView({ projectId }: { projectId: string }) {
  const navigate = useNavigate()
  const pushNotification = useNotificationStore((s) => s.push)
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [memberKey, setMemberKey] = useState('')
  const [memberRole, setMemberRole] = useState<'editor' | 'viewer'>('viewer')

  const fetchProject = useCallback(() => projectService.get(projectId), [projectId])

  useEffect(() => {
    fetchProject()
      .then(setProject)
      .catch((e) => {
        pushNotification({
          variant: 'destructive',
          message: e instanceof Error ? e.message : 'Gagal memuat proyek',
        })
      })
      .finally(() => setLoading(false))
    // pushNotification is a stable Zustand action; only refetch when projectId/fetchProject change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchProject])

  async function reload() {
    setProject(await projectService.get(projectId))
  }

  async function onAddMember() {
    if (!memberKey.trim()) return
    await projectService.addMember(projectId, memberKey, memberRole)
    setMemberKey('')
    await reload()
  }

  async function onRemoveMember(principalKey: string) {
    await projectService.removeMember(projectId, principalKey)
    await reload()
  }

  async function onArchive() {
    await projectService.archive(projectId)
    await reload()
    pushNotification({ variant: 'success', message: 'Proyek diarsipkan.' })
  }

  if (loading) {
    return <Skeleton className="h-32 w-full max-w-2xl" />
  }

  if (!project) {
    return (
      <p className="text-sm text-muted-foreground">
        Proyek tidak ditemukan atau Anda tidak punya akses.
      </p>
    )
  }

  const isOwner = project.your_role === 'owner'

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <button
        type="button"
        onClick={() => navigate('/projects')}
        className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={14} /> Semua Proyek
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          {project.description && (
            <p className="text-sm text-muted-foreground">{project.description}</p>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          <Badge variant="outline">{project.your_role}</Badge>
          {project.status === 'archived' && <Badge variant="outline">Diarsipkan</Badge>}
        </div>
      </div>

      <div className="flex gap-2">
        <Button size="sm" variant="outline" className="w-fit" onClick={() => navigate(`/projects/${projectId}/workspace`)}>
          <FolderKanban size={14} className="mr-1" /> Workspace
        </Button>
        {isOwner && project.status === 'active' && (
          <Button size="sm" variant="outline" className="w-fit" onClick={onArchive}>
            Arsipkan Proyek
          </Button>
        )}
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Anggota</h2>
        {project.members.length === 0 ? (
          <p className="text-sm text-muted-foreground">Hanya pemilik.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {project.members.map((m) => (
              <div
                key={m.principal_key}
                className="flex items-center justify-between rounded-lg border border-border p-3"
              >
                <span className="text-sm">{m.principal_key}</span>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{m.role}</Badge>
                  {isOwner && (
                    <button
                      type="button"
                      onClick={() => onRemoveMember(m.principal_key)}
                      aria-label={`Hapus ${m.principal_key}`}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {isOwner && (
          <div className="flex gap-2">
            <input
              value={memberKey}
              onChange={(e) => setMemberKey(e.target.value)}
              placeholder="API key anggota"
              className="flex-1 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
            />
            <select
              value={memberRole}
              onChange={(e) => setMemberRole(e.target.value as 'editor' | 'viewer')}
              className="rounded-md border border-input bg-transparent px-2 py-1.5 text-sm"
            >
              <option value="viewer">viewer</option>
              <option value="editor">editor</option>
            </select>
            <Button
              size="icon"
              onClick={onAddMember}
              disabled={!memberKey.trim()}
              aria-label="Tambah anggota"
            >
              <UserPlus size={16} />
            </Button>
          </div>
        )}
      </section>
    </div>
  )
}
