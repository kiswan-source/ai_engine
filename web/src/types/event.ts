/**
 * Canonical event union — EVENT_CATALOG.md §2. This is the *future* SSE
 * contract for the workflow/orchestrator adapter (IMPLEMENTATION_BLUEPRINT.md
 * §5 "SSE / Streaming"), which does not exist as a real endpoint yet — only
 * `/api/v1/orchestrator/run` (synchronous) is live today. `eventStream.ts`
 * and `workflowStore`/`agentStore` are written against this contract so they
 * only need a transport swap, not a rewrite, once the real endpoint ships.
 */
export type CanonicalEventName =
  | 'WorkflowCreated'
  | 'WorkflowStarted'
  | 'AgentAssigned'
  | 'AgentStarted'
  | 'AgentThinking'
  | 'ToolStarted'
  | 'ToolFinished'
  | 'WaitingApproval'
  | 'WorkflowCompleted'
  | 'WorkflowFailed'
  | 'HistorySaved'
  | 'NotificationCreated'

export interface CanonicalEvent {
  event: CanonicalEventName
  trace_id: string
  workflow_id: string
  timestamp: string
  data: Record<string, unknown>
}

/** Type guard — lets `eventStream.ts` fail soft on event names it doesn't know yet (EVENT_CATALOG.md §5.3). */
const KNOWN_EVENTS: ReadonlySet<string> = new Set([
  'WorkflowCreated',
  'WorkflowStarted',
  'AgentAssigned',
  'AgentStarted',
  'AgentThinking',
  'ToolStarted',
  'ToolFinished',
  'WaitingApproval',
  'WorkflowCompleted',
  'WorkflowFailed',
  'HistorySaved',
  'NotificationCreated',
])

export function isKnownEvent(name: string): name is CanonicalEventName {
  return KNOWN_EVENTS.has(name)
}
