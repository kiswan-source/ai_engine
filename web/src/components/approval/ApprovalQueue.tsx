import type { ApprovalRequest } from '@/types/approval'
import { ApprovalCard } from './ApprovalCard'

interface ApprovalQueueProps {
  approvals: ApprovalRequest[]
  decidingTraceId: string | null
  onDecide: (traceId: string, approved: boolean) => void
}

export function ApprovalQueue({ approvals, decidingTraceId, onDecide }: ApprovalQueueProps) {
  if (approvals.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">Tidak ada permintaan persetujuan saat ini.</p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {approvals.map((a) => (
        <ApprovalCard
          key={a.trace_id}
          approval={a}
          deciding={decidingTraceId === a.trace_id}
          onApprove={() => onDecide(a.trace_id, true)}
          onReject={() => onDecide(a.trace_id, false)}
        />
      ))}
    </div>
  )
}
