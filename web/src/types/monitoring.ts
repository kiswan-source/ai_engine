/** Real shapes returned by `api/routes/monitoring.py`, mirroring `telemetry/monitoring.py` exactly (Bab 62). */

export interface LatencyPercentiles {
  p50: number
  p95: number
  p99: number
}

export interface AgentDashboard {
  agents: string[]
  roles: string[]
  success_rate_by_role: Record<string, number>
  latency_ms_by_role: Record<string, LatencyPercentiles>
}

export interface WorkflowDashboard {
  state_counts: Record<string, number>
  escalation_rate: number
  success_rate: number
  avg_duration_ms: number
  by_mode: Record<string, LatencyPercentiles>
  completed: number
  failed: number
}

export interface CircuitBreakerSnapshot {
  state: 'closed' | 'open' | 'half_open'
  consecutive_failures: number
  failure_threshold: number
  recovery_timeout_s: number
  trial_requests: number
}

export interface ProviderDashboard {
  health: Record<string, unknown>
  error_rate: Record<string, number>
  latency_ms: Record<string, LatencyPercentiles>
  circuit_breaker: Record<string, CircuitBreakerSnapshot>
}

export interface CostDashboard {
  total_usd: number
  today_usd: number
  by_provider_usd: Record<string, number>
  by_role_usd: Record<string, number>
}

export interface LatencyDashboard {
  end_to_end_ms: LatencyPercentiles
  by_role_ms: Record<string, LatencyPercentiles>
  by_provider_ms: Record<string, LatencyPercentiles>
}

export interface HealthDashboard {
  ready: boolean
  checks: Record<string, unknown>
}

export interface QueueEntry {
  rq_length?: number
  rq_failed?: number
  rq_error?: string
  task_queue_length: number
}

export type QueueDashboard = Record<string, QueueEntry>

export interface AuditEntry {
  event_type: string
  actor: string
  detail: Record<string, unknown>
  trace_id: string
  timestamp: number
}

export interface SecurityDashboard {
  total_security_events: number
  by_type: Record<string, number>
  recent: AuditEntry[]
}

export interface AuditDashboard {
  total_entries: number
  by_event_type: Record<string, number>
  unique_actors: number
  recent: AuditEntry[]
}

export interface WorkspaceDashboard {
  total_workspaces: number
  active: number
  by_status: Record<string, number>
  document_count: number
  image_count: number
  gis_count: number
  total_size_bytes: number
  errors: string[]
}

/** `ImprovementRecommendation` (improvement/models.py) as returned by the ledger. */
export interface ImprovementRecommendationEntry {
  id: string
  created_at: number
  category: string
  severity: 'low' | 'medium' | 'high'
  evidence: Record<string, unknown>
  suggestion: string
  setting: string | null
  suggested_value: number | null
}

/** `ImprovementAction` (improvement/models.py) as returned by the ledger. */
export interface ImprovementActionEntry {
  id: string
  recommendation_id: string
  created_at: number
  setting: string
  old_value: number
  new_value: number
  commit_sha: string
  review_after: number
  reviewed_at: number | null
  outcome: 'kept' | 'reverted' | null
  revert_commit_sha: string | null
}

/** Fase 7, DCF v5 mandate "Continuous Improvement Engine" — sourced from
 * `improvement/ledger.py` via `telemetry/monitoring.py::improvement_dashboard()`. */
export interface ImprovementDashboard {
  total_recommendations: number
  total_actions_applied: number
  total_actions_reviewed: number
  pending_review: ImprovementActionEntry[]
  recent_recommendations: ImprovementRecommendationEntry[]
  recent_actions_reviewed: ImprovementActionEntry[]
  ledger_integrity_ok: boolean
  ledger_integrity_problems: string[]
}

export interface MonitoringDashboard {
  agent: AgentDashboard
  workflow: WorkflowDashboard
  provider: ProviderDashboard
  cost: CostDashboard
  latency: LatencyDashboard
  health: HealthDashboard
  queue: QueueDashboard
  workspace: WorkspaceDashboard
  security: SecurityDashboard
  audit: AuditDashboard
  improvement: ImprovementDashboard
}

export interface MonitoringAlert {
  kind: string
  message: string
  value: number
  threshold: number
}
