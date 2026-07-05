/**
 * Agent State (IMPLEMENTATION_BLUEPRINT.md §7) — "who is doing what" for the
 * optional Multi-Agent panel (AI_WORKSPACE_ARCHITECTURE.md §2, §8 — generic
 * over agent count/names, never hardcoded). Updated via `applyEvent()` only.
 */
import { create } from 'zustand'
import type { CanonicalEvent } from '@/types/event'
import { AGENT_ROLE_LABEL } from '@/types/workflow'

export interface ActiveAgentStep {
  role: string
  label: string
  status: 'assigned' | 'started' | 'thinking' | 'tool_running' | 'done'
  toolName?: string
}

interface AgentStoreState {
  activeSteps: ActiveAgentStep[]
  reset: () => void
  applyEvent: (event: CanonicalEvent) => void
}

function upsert(
  steps: ActiveAgentStep[],
  role: string,
  patch: Partial<ActiveAgentStep>,
): ActiveAgentStep[] {
  const idx = steps.findIndex((s) => s.role === role)
  const label = AGENT_ROLE_LABEL[role] ?? role
  if (idx === -1) return [...steps, { role, label, status: 'assigned', ...patch }]
  const next = [...steps]
  next[idx] = { ...next[idx], ...patch }
  return next
}

export const useAgentStore = create<AgentStoreState>((set) => ({
  activeSteps: [],
  reset: () => set({ activeSteps: [] }),
  applyEvent: (event) =>
    set((s) => {
      const role = (event.data.agent_role as string) ?? ''
      switch (event.event) {
        case 'AgentAssigned':
          return { activeSteps: upsert(s.activeSteps, role, { status: 'assigned' }) }
        case 'AgentStarted':
          return { activeSteps: upsert(s.activeSteps, role, { status: 'started' }) }
        case 'AgentThinking':
          return { activeSteps: upsert(s.activeSteps, role, { status: 'thinking' }) }
        case 'ToolStarted':
          return {
            activeSteps: upsert(s.activeSteps, role, {
              status: 'tool_running',
              toolName: event.data.tool_name as string | undefined,
            }),
          }
        case 'ToolFinished':
          return { activeSteps: upsert(s.activeSteps, role, { status: 'started' }) }
        default:
          return s
      }
    }),
}))
