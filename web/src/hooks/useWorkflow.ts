/**
 * Runs a multi-agent workflow against the real `/api/v1/orchestrator/run`
 * (synchronous today — see `workflowService.ts`) and feeds the result into
 * `workflowStore` — the "Timeline minimal" adapter of
 * READY_FOR_IMPLEMENTATION.md §3 step 5.
 */
import { useCallback, useState } from 'react'
import { workflowService } from '@/services/workflowService'
import { useWorkflowStore } from '@/stores/workflowStore'
import type { WorkflowRunRequest } from '@/types/workflow'

export function useWorkflow() {
  const [error, setError] = useState<string | null>(null)
  const setRunning = useWorkflowStore((s) => s.setRunning)
  const setFromRunResult = useWorkflowStore((s) => s.setFromRunResult)
  const status = useWorkflowStore((s) => s.status)

  const run = useCallback(
    async (req: WorkflowRunRequest) => {
      setError(null)
      setRunning(crypto.randomUUID())
      try {
        const result = await workflowService.run(req)
        setFromRunResult(result)
        return result
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Workflow run failed')
        throw e
      }
    },
    [setRunning, setFromRunResult],
  )

  return { run, status, error, isRunning: status === 'executing' || status === 'planning' }
}
