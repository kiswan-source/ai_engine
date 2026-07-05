/** Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — decision is delegated via callbacks. */
import { Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { ApprovalRequest } from '@/types/approval'

interface ApprovalCardProps {
  approval: ApprovalRequest
  onApprove: () => void
  onReject: () => void
  deciding?: boolean
}

export function ApprovalCard({ approval, onApprove, onReject, deciding }: ApprovalCardProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base font-medium">
          Trace {approval.trace_id.slice(0, 8)}
        </CardTitle>
        <Badge variant="outline" className="gap-1 text-warning">
          <Clock size={12} />
          Menunggu Diproses
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{approval.reason}</p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onReject} disabled={deciding}>
            Tolak
          </Button>
          <Button size="sm" onClick={onApprove} disabled={deciding}>
            Setujui
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
