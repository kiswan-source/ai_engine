/**
 * Talks to `/api/v1/orchestrator/*` (api/routes/orchestrator.py — not a
 * protected foundation, Bab 45.1, but the real live endpoint today; not the
 * `workflow.py`/`orchestrator.py` split API_CONTRACT.md §3.1/3.2 planned).
 */
import { apiClient } from './apiClient'
import type { WorkflowRunRequest, WorkflowRunResult } from '@/types/workflow'
import type { ApprovalRequest, ApprovalDecisionRequest } from '@/types/approval'

export const workflowService = {
  listRoles: () => apiClient.get<{ roles: string[] }>('/api/v1/orchestrator/roles'),
  listModes: () => apiClient.get<{ modes: string[] }>('/api/v1/orchestrator/modes'),
  /** Synchronous today — blocks until the whole workflow finishes (no incremental step events yet). */
  run: (req: WorkflowRunRequest) =>
    apiClient.post<WorkflowRunResult>('/api/v1/orchestrator/run', req),
  listPendingApprovals: () =>
    apiClient.get<{ approvals: ApprovalRequest[] }>('/api/v1/orchestrator/approvals'),
  decideApproval: (traceId: string, decision: ApprovalDecisionRequest) =>
    apiClient.post<{ trace_id: string; state: string }>(
      `/api/v1/orchestrator/approvals/${encodeURIComponent(traceId)}/decide`,
      decision,
    ),
}
