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

export interface MonitoringDashboard {
  agent: AgentDashboard
  workflow: WorkflowDashboard
  provider: ProviderDashboard
  cost: CostDashboard
  latency: LatencyDashboard
  health: HealthDashboard
  queue: QueueDashboard
}

export interface MonitoringAlert {
  kind: string
  message: string
  value: number
  threshold: number
}
