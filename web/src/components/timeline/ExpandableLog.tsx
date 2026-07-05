/**
 * Raw technical detail behind a Timeline step — hidden by default, opened
 * only on request (AI_WORKSPACE_ARCHITECTURE.md §6.1 "Expandable Log",
 * §6.3 rule 1: technical detail is always one click away, never forced).
 */
import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { WorkflowStep } from '@/stores/workflowStore'

export function ExpandableLog({ steps }: { steps: WorkflowStep[] }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-2 border-t border-border pt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        Lihat Detail Teknis
      </button>
      {open && (
        <pre className="mt-2 max-h-64 overflow-y-auto rounded-md bg-muted p-3 text-xs text-muted-foreground">
          {JSON.stringify(steps, null, 2)}
        </pre>
      )}
    </div>
  )
}
