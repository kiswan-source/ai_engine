/**
 * One Timeline step (AI_WORKSPACE_ARCHITECTURE.md §6.2 sketch,
 * DESIGN_SYSTEM.md §8 visual spec). Only the "running" step animates —
 * keeps many-step timelines from feeling noisy.
 */
import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { WorkflowStep } from '@/stores/workflowStore'

const ICONS = {
  done: CheckCircle2,
  running: Loader2,
  pending: Circle,
  failed: AlertCircle,
} as const

const COLORS = {
  done: 'text-success',
  running: 'text-info',
  pending: 'text-muted-foreground',
  failed: 'text-destructive',
} as const

const STATUS_LABEL = {
  done: 'Selesai',
  running: 'Berjalan',
  pending: 'Menunggu',
  failed: 'Gagal',
} as const

export function StepIndicator({ step }: { step: WorkflowStep }) {
  const Icon = ICONS[step.status]

  return (
    <div className="flex items-center gap-3 py-1.5">
      <Icon
        size={18}
        className={cn(COLORS[step.status], step.status === 'running' && 'animate-spin')}
      />
      <span className={cn('text-sm', step.status === 'pending' && 'text-muted-foreground')}>
        {step.label}
      </span>
      <span className="ml-auto text-xs uppercase tracking-wide text-muted-foreground">
        {STATUS_LABEL[step.status]}
      </span>
    </div>
  )
}
