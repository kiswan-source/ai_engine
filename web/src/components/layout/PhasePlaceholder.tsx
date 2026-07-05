/** Shared shell for areas not yet built out — honest about why, per Feature Readiness Matrix (IMPLEMENTATION_BLUEPRINT.md §3). */
interface PhasePlaceholderProps {
  title: string
  phase: 'Phase 2' | 'Phase 3'
  reason: string
}

export function PhasePlaceholder({ title, phase, reason }: PhasePlaceholderProps) {
  return (
    <div className="flex max-w-2xl flex-col gap-2">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="text-sm text-muted-foreground">
        Dijadwalkan {phase} — {reason}
      </p>
    </div>
  )
}
