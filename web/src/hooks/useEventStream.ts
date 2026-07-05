/**
 * Subscribes the current component to the canonical event stream for one
 * `trace_id` and routes events into `workflowStore`/`agentStore` via
 * `applyEvent()` (FRONTEND_ARCHITECTURE.md §4). Not used yet in Phase 1
 * pages — the real SSE endpoint doesn't exist (`services/eventStream.ts`
 * docstring) — but wired so pages can switch from polling to this with a
 * one-line change once it does.
 */
import { useEffect } from 'react'
import { connectEventStream } from '@/services/eventStream'
import { useWorkflowStore } from '@/stores/workflowStore'
import { useAgentStore } from '@/stores/agentStore'

export function useEventStream(traceId: string | null) {
  const applyWorkflowEvent = useWorkflowStore((s) => s.applyEvent)
  const applyAgentEvent = useAgentStore((s) => s.applyEvent)

  useEffect(() => {
    if (!traceId) return
    const handle = connectEventStream(traceId, (event) => {
      applyWorkflowEvent(event)
      applyAgentEvent(event)
    })
    return () => handle.close()
  }, [traceId, applyWorkflowEvent, applyAgentEvent])
}
