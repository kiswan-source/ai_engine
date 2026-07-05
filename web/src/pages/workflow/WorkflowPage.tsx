/**
 * Timeline minimal (READY_FOR_IMPLEMENTATION.md §3 step 5) — polls the real
 * synchronous `/api/v1/orchestrator/run` rather than the not-yet-built SSE
 * stream (see `useWorkflow.ts`/`eventStream.ts` docstrings).
 */
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { StepIndicator } from '@/components/timeline/StepIndicator'
import { ExpandableLog } from '@/components/timeline/ExpandableLog'
import { useWorkflow } from '@/hooks/useWorkflow'
import { useWorkflowStore } from '@/stores/workflowStore'
import { workflowService } from '@/services/workflowService'
import { WORKFLOW_STATE_LABEL } from '@/types/workflow'

export default function WorkflowPage() {
  const [roles, setRoles] = useState<string[]>([])
  const [modes, setModes] = useState<string[]>([])
  const [selectedRoles, setSelectedRoles] = useState<string[]>([])
  const [mode, setMode] = useState('sequential')
  const [prompt, setPrompt] = useState('')

  const { run, isRunning, error } = useWorkflow()
  const steps = useWorkflowStore((s) => s.steps)
  const status = useWorkflowStore((s) => s.status)

  useEffect(() => {
    workflowService.listRoles().then((r) => setRoles(r.roles))
    workflowService.listModes().then((m) => {
      setModes(m.modes)
      if (m.modes.length > 0) setMode(m.modes[0])
    })
  }, [])

  function toggleRole(role: string) {
    setSelectedRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role],
    )
  }

  function onRun() {
    if (!prompt.trim() || selectedRoles.length === 0) return
    void run({ prompt, roles: selectedRoles, mode })
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Workflow</h1>
        <p className="text-sm text-muted-foreground">
          Menyusun tim AI (peran &amp; pola eksekusi) untuk satu pekerjaan.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium">Peran yang dilibatkan</label>
        <div className="flex flex-wrap gap-2">
          {roles.map((role) => (
            <button
              key={role}
              type="button"
              onClick={() => toggleRole(role)}
              className={`rounded-full border px-3 py-1 text-xs ${
                selectedRoles.includes(role)
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border text-muted-foreground'
              }`}
            >
              {role}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium" htmlFor="mode-select">
          Pola eksekusi
        </label>
        <select
          id="mode-select"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="w-fit rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
        >
          {modes.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={3}
        placeholder="Apa yang perlu dikerjakan?"
        className="resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
      />

      <Button
        onClick={onRun}
        disabled={isRunning || !prompt.trim() || selectedRoles.length === 0}
        className="w-fit"
      >
        {isRunning && <Loader2 size={16} className="mr-2 animate-spin" />}
        Jalankan Workflow
      </Button>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {steps.length > 0 && (
        <div className="rounded-lg border border-border p-4">
          <p className="mb-2 text-sm font-medium">
            Status: {status !== 'idle' ? WORKFLOW_STATE_LABEL[status] : '—'}
          </p>
          {steps.map((step) => (
            <StepIndicator key={step.stepId} step={step} />
          ))}
          <ExpandableLog steps={steps} />
        </div>
      )}
    </div>
  )
}
