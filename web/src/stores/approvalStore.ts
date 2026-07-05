/**
 * Approval State (IMPLEMENTATION_BLUEPRINT.md §7). Per §7.2 rule 2, a
 * user's approve/reject decision is the *one* direct user write into this
 * category — everything else (the queue itself) is reactive to the backend
 * (here: polled from the real `/api/v1/orchestrator/approvals`, per
 * `workflowService.ts`).
 */
import { create } from 'zustand'
import type { ApprovalRequest } from '@/types/approval'

interface ApprovalState {
  pending: ApprovalRequest[]
  setPending: (approvals: ApprovalRequest[]) => void
  removeByTraceId: (traceId: string) => void
}

export const useApprovalStore = create<ApprovalState>((set) => ({
  pending: [],
  setPending: (pending) => set({ pending }),
  removeByTraceId: (traceId) =>
    set((s) => ({ pending: s.pending.filter((a) => a.trace_id !== traceId) })),
}))
