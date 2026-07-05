/** `workflows/approval.py` `ApprovalRequest`, as returned by GET /api/v1/orchestrator/approvals. */
export interface ApprovalRequest {
  trace_id: string
  reason: string
  requested_at: number
  sla_seconds: number
  decided: boolean
  approved: boolean | null
  decided_by: string
  decision_reason: string
  decided_at: number | null
}

export interface ApprovalDecisionRequest {
  approved: boolean
  decided_by: string
  reason?: string
}
