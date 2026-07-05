/**
 * Approval minimal (READY_FOR_IMPLEMENTATION.md §3 step 6) — polls the real
 * `/api/v1/orchestrator/approvals` (no dedicated Approval endpoint exists
 * yet per API_CONTRACT.md §3.5, but this orchestrator endpoint already
 * covers the same shape: list pending + decide).
 */
import { useCallback, useEffect, useState } from 'react'
import { ApprovalQueue } from '@/components/approval/ApprovalQueue'
import { useApprovalStore } from '@/stores/approvalStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { workflowService } from '@/services/workflowService'

const POLL_INTERVAL_MS = 5000

export default function ApprovalPage() {
  const pending = useApprovalStore((s) => s.pending)
  const setPending = useApprovalStore((s) => s.setPending)
  const removeByTraceId = useApprovalStore((s) => s.removeByTraceId)
  const pushNotification = useNotificationStore((s) => s.push)
  const [decidingTraceId, setDecidingTraceId] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const { approvals } = await workflowService.listPendingApprovals()
      setPending(approvals)
    } catch {
      // Transient poll failure — next tick retries; not worth a toast every 5s.
    }
  }, [setPending])

  useEffect(() => {
    void refresh()
    const id = setInterval(refresh, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [refresh])

  async function onDecide(traceId: string, approved: boolean) {
    setDecidingTraceId(traceId)
    try {
      await workflowService.decideApproval(traceId, { approved, decided_by: 'workspace-user' })
      removeByTraceId(traceId)
      pushNotification({
        variant: approved ? 'success' : 'warning',
        message: approved ? 'Permintaan disetujui.' : 'Permintaan ditolak.',
      })
    } catch (e) {
      pushNotification({
        variant: 'destructive',
        message: e instanceof Error ? e.message : 'Gagal mengirim keputusan',
      })
    } finally {
      setDecidingTraceId(null)
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Approval</h1>
        <p className="text-sm text-muted-foreground">Pekerjaan yang menunggu keputusan Anda.</p>
      </div>
      <ApprovalQueue approvals={pending} decidingTraceId={decidingTraceId} onDecide={onDecide} />
    </div>
  )
}
