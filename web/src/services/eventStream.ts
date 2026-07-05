/**
 * SSE client for the canonical Workflow/Agent event stream
 * (API_CONTRACT.md §4, EVENT_CATALOG.md §3) — `GET /api/v1/stream?trace_id=...`.
 *
 * This endpoint does not exist in the backend yet (IMPLEMENTATION_BLUEPRINT.md
 * §9 marks the SSE adapter "Perlu Baru"); `workflowStore`/`agentStore` poll
 * `workflowService.run()` in the meantime (READY_FOR_IMPLEMENTATION.md §3
 * step 5, "Timeline versi minimal"). This module exists now so wiring in the
 * real stream later is a call-site swap, not a rewrite: `connectEventStream`
 * already does the one allowed thing a frontend may do with events — parse
 * and route them (FRONTEND_ARCHITECTURE.md §9) — nothing here decides
 * workflow/business logic.
 */
import { isKnownEvent, type CanonicalEvent } from '@/types/event'

export interface EventStreamHandle {
  close: () => void
}

/**
 * Opens one SSE connection scoped to a single `trace_id`/`workflow_id`
 * (AI_WORKSPACE_ARCHITECTURE.md §5.2 — frontend subscribes per in-flight
 * job, never to the global firehose). Unknown event names are dropped with
 * a console warning rather than thrown (EVENT_CATALOG.md §5.3 "fail soft").
 */
export function connectEventStream(
  traceId: string,
  onEvent: (event: CanonicalEvent) => void,
  onError?: (err: Event) => void,
): EventStreamHandle {
  const source = new EventSource(`/api/v1/stream?trace_id=${encodeURIComponent(traceId)}`)

  source.onmessage = (msg) => {
    try {
      const parsed = JSON.parse(msg.data) as CanonicalEvent
      if (!isKnownEvent(parsed.event)) {
        console.warn(
          `[eventStream] unknown event "${parsed.event}" — ignored, not applied to any store`,
        )
        return
      }
      onEvent(parsed)
    } catch {
      // Malformed frame — ignore rather than crash the subscriber.
    }
  }
  source.onerror = (err) => {
    onError?.(err)
  }

  return {
    close: () => source.close(),
  }
}
