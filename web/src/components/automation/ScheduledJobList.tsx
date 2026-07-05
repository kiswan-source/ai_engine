/** Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — all actions delegated via callbacks. */
import { Play, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatInterval } from '@/lib/utils'
import type { ScheduledJob } from '@/types/automation'

interface ScheduledJobListProps {
  jobs: ScheduledJob[]
  runningId: string | null
  onToggleEnabled: (job: ScheduledJob) => void
  onRunNow: (job: ScheduledJob) => void
  onDelete: (job: ScheduledJob) => void
}

const STATUS_BADGE = {
  success: { variant: 'outline', className: 'text-success', label: 'Selesai' },
  failed: { variant: 'outline', className: 'text-destructive', label: 'Gagal' },
} as const

export function ScheduledJobList({
  jobs,
  runningId,
  onToggleEnabled,
  onRunNow,
  onDelete,
}: ScheduledJobListProps) {
  if (jobs.length === 0) {
    return <p className="text-sm text-muted-foreground">Belum ada workflow terjadwal.</p>
  }

  return (
    <div className="flex flex-col gap-2">
      {jobs.map((job) => {
        const statusBadge = job.last_status ? STATUS_BADGE[job.last_status] : null
        return (
          <div key={job.id} className="flex flex-col gap-2 rounded-lg border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{job.name}</p>
                <p className="text-xs text-muted-foreground">
                  {formatInterval(job.interval_seconds)} · {job.roles.join(', ')}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {statusBadge && (
                  <Badge variant={statusBadge.variant} className={statusBadge.className}>
                    {statusBadge.label}
                  </Badge>
                )}
                <Badge
                  variant="outline"
                  className={job.enabled ? 'text-success' : 'text-muted-foreground'}
                >
                  {job.enabled ? 'Aktif' : 'Nonaktif'}
                </Badge>
              </div>
            </div>

            {job.last_result_summary && (
              <p className="truncate text-xs text-muted-foreground">{job.last_result_summary}</p>
            )}

            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => onRunNow(job)}
                disabled={runningId === job.id}
              >
                <Play size={14} className="mr-1" />
                {runningId === job.id ? 'Menjalankan…' : 'Jalankan Sekarang'}
              </Button>
              <Button size="sm" variant="outline" onClick={() => onToggleEnabled(job)}>
                {job.enabled ? 'Nonaktifkan' : 'Aktifkan'}
              </Button>
              <button
                type="button"
                onClick={() => onDelete(job)}
                aria-label={`Hapus ${job.name}`}
                className="ml-auto text-muted-foreground hover:text-destructive"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
