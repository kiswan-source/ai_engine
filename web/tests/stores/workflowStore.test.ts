import { describe, it, expect, beforeEach } from 'vitest'
import { useWorkflowStore } from '@/stores/workflowStore'
import type { WorkflowRunResult } from '@/types/workflow'
import type { CanonicalEvent } from '@/types/event'

function makeEvent(
  event: CanonicalEvent['event'],
  data: Record<string, unknown> = {},
): CanonicalEvent {
  return { event, trace_id: 't1', workflow_id: 'w1', timestamp: new Date().toISOString(), data }
}

describe('workflowStore', () => {
  beforeEach(() => {
    useWorkflowStore.getState().reset()
  })

  it('applyEvent moves status through the canonical event lifecycle', () => {
    const { applyEvent } = useWorkflowStore.getState()

    applyEvent(makeEvent('WorkflowCreated'))
    expect(useWorkflowStore.getState().status).toBe('planning')
    expect(useWorkflowStore.getState().activeWorkflowId).toBe('w1')

    applyEvent(makeEvent('WaitingApproval'))
    expect(useWorkflowStore.getState().status).toBe('reviewing')

    applyEvent(makeEvent('WorkflowCompleted'))
    expect(useWorkflowStore.getState().status).toBe('completed')
  })

  it('ignores events it does not recognize (fail soft, EVENT_CATALOG.md §5.3)', () => {
    const { applyEvent } = useWorkflowStore.getState()
    applyEvent(makeEvent('WorkflowCreated'))
    const before = useWorkflowStore.getState()
    // @ts-expect-error deliberately unknown event name for the fail-soft test
    applyEvent(makeEvent('SomeFutureEvent'))
    expect(useWorkflowStore.getState()).toEqual(before)
  })

  it('setFromRunResult derives steps from the synchronous /run response', () => {
    const result: WorkflowRunResult = {
      mode: 'sequential',
      trace_id: 't2',
      final_output: 'done',
      results: [
        {
          output: 'ok',
          confidence: 0.9,
          trace_id: 't2',
          provider_used: 'ollama',
          model_used: 'gemma',
          cost: 0,
          agent_id: 'a1',
          role: 'planner',
          degraded: false,
          error: null,
          prompt_tokens: 10,
          completion_tokens: 20,
        },
      ],
      step_outputs: {},
      degraded: false,
      failed: false,
      escalate: false,
      guardrail_blocked: false,
      state: 'completed',
    }

    useWorkflowStore.getState().setFromRunResult(result)
    const { steps, status, activeWorkflowId } = useWorkflowStore.getState()

    expect(activeWorkflowId).toBe('t2')
    expect(status).toBe('completed')
    expect(steps).toHaveLength(1)
    expect(steps[0]).toMatchObject({
      agentRole: 'planner',
      status: 'done',
      label: 'Menyusun Rencana',
    })
  })
})
