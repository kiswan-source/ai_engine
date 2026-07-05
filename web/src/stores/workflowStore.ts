/**
 * Workflow State (IMPLEMENTATION_BLUEPRINT.md §7) — status of the
 * in-flight/last job, feeding the Timeline (AI_WORKSPACE_ARCHITECTURE.md §6).
 *
 * Per FRONTEND_ARCHITECTURE.md §4, this store should only be mutated via
 * `applyEvent()` fed by `services/eventStream.ts`. That canonical SSE
 * endpoint doesn't exist yet (see `eventStream.ts` docstring), so Phase 1
 * "Timeline minimal" (READY_FOR_IMPLEMENTATION.md §3 step 5) also exposes
 * `setFromRunResult`, fed by polling `workflowService.run()` — a deliberate,
 * documented interim exception, not a component reaching in with `set()`.
 */
import { create } from 'zustand'
import type { CanonicalEvent } from '@/types/event'
import type { AgentResult, WorkflowRunResult, WorkflowState } from '@/types/workflow'
import { AGENT_ROLE_LABEL } from '@/types/workflow'

export interface WorkflowStep {
  stepId: string
  agentRole: string
  label: string
  status: 'done' | 'running' | 'pending' | 'failed'
  result?: AgentResult
}

interface WorkflowStoreState {
  activeWorkflowId: string | null
  status: WorkflowState | 'idle'
  steps: WorkflowStep[]
  lastResult: WorkflowRunResult | null
  reset: () => void
  applyEvent: (event: CanonicalEvent) => void
  setFromRunResult: (result: WorkflowRunResult) => void
  setRunning: (traceId: string) => void
}

export const useWorkflowStore = create<WorkflowStoreState>((set) => ({
  activeWorkflowId: null,
  status: 'idle',
  steps: [],
  lastResult: null,

  reset: () => set({ activeWorkflowId: null, status: 'idle', steps: [], lastResult: null }),

  setRunning: (traceId) =>
    set({ activeWorkflowId: traceId, status: 'executing', steps: [], lastResult: null }),

  setFromRunResult: (result) =>
    set({
      activeWorkflowId: result.trace_id,
      status: result.state ?? (result.failed ? 'failed' : 'completed'),
      lastResult: result,
      steps: result.results.map((r, i) => ({
        stepId: `${result.trace_id}-${i}`,
        agentRole: r.role,
        label: AGENT_ROLE_LABEL[r.role] ?? r.role,
        status: r.error ? 'failed' : 'done',
        result: r,
      })),
    }),

  // EVENT_CATALOG.md §4 mapping — kept ready for when the real SSE stream lands.
  applyEvent: (event) =>
    set((s) => {
      switch (event.event) {
        case 'WorkflowCreated':
        case 'WorkflowStarted':
          return { activeWorkflowId: event.workflow_id, status: 'planning' }
        case 'WaitingApproval':
          return { status: 'reviewing' }
        case 'WorkflowCompleted':
          return { status: 'completed' }
        case 'WorkflowFailed':
          return { status: 'failed' }
        default:
          return s
      }
    }),
}))
