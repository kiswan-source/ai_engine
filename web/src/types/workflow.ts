/**
 * Real shapes served by `api/routes/orchestrator.py` today (verified against
 * `orchestrator/task_manager.py` `State`, `agents/base_agent.py` `AgentResult`,
 * and `workflows/base.py` `WorkflowResult` — not the placeholder schema in
 * API_CONTRACT.md §3.1/3.2, which describes a `workflow.py`/`orchestrator.py`
 * pair that hasn't been built the way that doc assumed).
 */

/** Bab 49.1 task/workflow states, as emitted by `task_manager.State` (lower snake_case, not the Title Case in API_CONTRACT.md). */
export type WorkflowState =
  | 'pending'
  | 'planning'
  | 'research'
  | 'executing'
  | 'reviewing'
  | 'approved'
  | 'completed'
  | 'cancelled'
  | 'failed'
  | 'retry'
  | 'rollback'

/** AI_WORKSPACE_ARCHITECTURE.md §4.2 — backend state to user-facing label, one mapping used everywhere (Timeline, History, Badge colors). */
export const WORKFLOW_STATE_LABEL: Record<WorkflowState, string> = {
  pending: 'Menunggu Diproses',
  planning: 'Menyusun Rencana',
  research: 'Sedang Dikerjakan',
  executing: 'Sedang Dikerjakan',
  reviewing: 'Sedang Ditinjau',
  approved: 'Disetujui',
  completed: 'Selesai',
  cancelled: 'Dibatalkan',
  failed: 'Gagal — Dicoba Ulang',
  retry: 'Gagal — Dicoba Ulang',
  rollback: 'Dikembalikan ke Kondisi Semula',
}

/** DESIGN_SYSTEM.md §2 — status color token per state. */
export const WORKFLOW_STATE_COLOR: Record<
  WorkflowState,
  'success' | 'warning' | 'destructive' | 'info'
> = {
  pending: 'warning',
  planning: 'info',
  research: 'info',
  executing: 'info',
  reviewing: 'info',
  approved: 'success',
  completed: 'success',
  cancelled: 'warning',
  failed: 'destructive',
  retry: 'destructive',
  rollback: 'warning',
}

/** `agents/base_agent.py` `AgentResult`, as returned inside `WorkflowResult`. */
export interface AgentResult {
  output: string
  confidence: number
  trace_id: string
  provider_used: string
  model_used: string
  cost: number
  agent_id: string
  role: string
  degraded: boolean
  error: string | null
  prompt_tokens: number
  completion_tokens: number
}

/** AI_WORKSPACE_ARCHITECTURE.md §4.1 — backend role to user-facing label ("Menyusun Rencana", not "Planner"). */
export const AGENT_ROLE_LABEL: Record<string, string> = {
  planner: 'Menyusun Rencana',
  research: 'Mengumpulkan Informasi',
  analyst: 'Menganalisis Data',
  writer: 'Menulis Dokumen',
  reviewer: 'Memeriksa Kualitas',
  memory: 'Mengingat Konteks',
  guardrail: 'Memeriksa Keamanan Konten',
  tool: 'Menjalankan Alat Bantu',
  vision: 'Membaca Gambar/Dokumen',
  reflection: 'Meninjau Ulang Hasil',
  critic: 'Mencari Kekurangan',
  consensus: 'Menyatukan Hasil',
  confidence: 'Menilai Tingkat Keyakinan',
}

/** POST /api/v1/orchestrator/run response — `{**asdict(WorkflowResult), state}` (api/routes/orchestrator.py). */
export interface WorkflowRunResult {
  mode: string
  trace_id: string
  final_output: string
  results: AgentResult[]
  step_outputs: Record<string, AgentResult>
  degraded: boolean
  failed: boolean
  escalate: boolean
  guardrail_blocked: boolean
  state: WorkflowState | null
}

export interface WorkflowRunRequest {
  prompt: string
  roles: string[]
  mode?: string
  system?: string
  temperature?: number
  max_tokens?: number
  /** Vision (Bab 17.1 role) — data: URIs, exactly what FileReader.readAsDataURL() produces. */
  images?: string[]
}
