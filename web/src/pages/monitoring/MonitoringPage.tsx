/**
 * Monitoring — `telemetry/monitoring.py`'s dashboards (Bab 62), minus Memory
 * (see `api/routes/monitoring.py` docstring for why). Polls every 5s like
 * ApprovalPage; local page state only — Monitoring isn't one of the 11
 * canonical state categories (IMPLEMENTATION_BLUEPRINT.md §7), it's a
 * read-only operational view.
 */
import { useCallback, useEffect, useState } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { StatTile } from '@/components/monitoring/StatTile'
import { StatusBadge, type StatusVariant } from '@/components/monitoring/StatusBadge'
import { monitoringService } from '@/services/monitoringService'
import type { MonitoringDashboard, MonitoringAlert } from '@/types/monitoring'
import { formatUsd, formatMs, formatPercent } from '@/lib/utils'

const POLL_INTERVAL_MS = 5000

function classifyHealthValue(value: unknown): { variant: StatusVariant; label: string } {
  if (value && typeof value === 'object' && 'ollama' in value) {
    const ok = (value as { ollama: string }).ollama === 'ok'
    return ok ? { variant: 'success', label: 'ok' } : { variant: 'destructive', label: 'error' }
  }
  if (value === 'ok') return { variant: 'success', label: 'ok' }
  return { variant: 'destructive', label: typeof value === 'string' ? value : 'error' }
}

function classifyCircuitState(state: string): { variant: StatusVariant; label: string } {
  if (state === 'closed') return { variant: 'success', label: 'closed' }
  if (state === 'half_open') return { variant: 'warning', label: 'half-open' }
  return { variant: 'destructive', label: 'open' }
}

export default function MonitoringPage() {
  const [dashboard, setDashboard] = useState<MonitoringDashboard | null>(null)
  const [alerts, setAlerts] = useState<MonitoringAlert[]>([])
  const [loading, setLoading] = useState(true)

  // Pure fetch, no setState here — the effect below applies the result
  // inline via .then()/.finally() on each tick (react-hooks/set-state-in-effect
  // flags a plain useState setter reached through a locally-defined async
  // helper; it doesn't trace into Zustand actions, which is why
  // ApprovalPage's near-identical poll loop doesn't need this split).
  const fetchAll = useCallback(async () => {
    const [dashboardRes, alertsRes] = await Promise.all([
      monitoringService.getDashboard(),
      monitoringService.getAlerts(),
    ])
    return { dashboard: dashboardRes, alerts: alertsRes.alerts }
  }, [])

  useEffect(() => {
    let cancelled = false
    function tick() {
      fetchAll()
        .then(({ dashboard, alerts }) => {
          if (cancelled) return
          setDashboard(dashboard)
          setAlerts(alerts)
        })
        .catch(() => {
          // Transient poll failure — next tick retries.
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }
    tick()
    const id = setInterval(tick, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [fetchAll])

  if (loading || !dashboard) {
    return (
      <div className="flex max-w-3xl flex-col gap-2">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  const providerNames = Object.keys(dashboard.provider.health)
  const queueNames = Object.keys(dashboard.queue)

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Monitoring</h1>
          <p className="text-sm text-muted-foreground">
            Kesehatan, biaya, dan performa sistem — hanya untuk peran teknis/admin.
          </p>
        </div>
        <StatusBadge
          variant={dashboard.health.ready ? 'success' : 'destructive'}
          label={dashboard.health.ready ? 'Sistem Sehat' : 'Perlu Perhatian'}
        />
      </div>

      {alerts.length > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-warning/50 bg-warning/10 p-4">
          {alerts.map((a) => (
            <p key={a.kind} className="text-sm text-warning-foreground">
              {a.message}
            </p>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatTile label="Biaya total" value={formatUsd(dashboard.cost.total_usd)} />
        <StatTile label="Biaya hari ini" value={formatUsd(dashboard.cost.today_usd)} />
        <StatTile label="Latensi p50" value={formatMs(dashboard.latency.end_to_end_ms.p50)} />
        <StatTile label="Latensi p95" value={formatMs(dashboard.latency.end_to_end_ms.p95)} />
        <StatTile
          label="Tingkat keberhasilan workflow"
          value={formatPercent(dashboard.workflow.success_rate)}
        />
        <StatTile
          label="Tingkat eskalasi"
          value={formatPercent(dashboard.workflow.escalation_rate)}
        />
        <StatTile label="Agent terdaftar" value={String(dashboard.agent.agents.length)} />
        <StatTile label="Workflow selesai" value={String(dashboard.workflow.completed)} />
        <StatTile label="Workflow gagal" value={String(dashboard.workflow.failed)} />
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Provider</h2>
        <div className="flex flex-col gap-2">
          {providerNames.map((name) => {
            const health = classifyHealthValue(dashboard.provider.health[name])
            const breaker = dashboard.provider.circuit_breaker[name]
            const errorRate = dashboard.provider.error_rate[name]
            return (
              <div
                key={name}
                className="flex items-center justify-between rounded-lg border border-border p-3"
              >
                <span className="text-sm font-medium capitalize">{name}</span>
                <div className="flex items-center gap-2">
                  {errorRate !== undefined && (
                    <span className="text-xs text-muted-foreground">
                      Error {formatPercent(errorRate)}
                    </span>
                  )}
                  {breaker && <StatusBadge {...classifyCircuitState(breaker.state)} />}
                  <StatusBadge {...health} />
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Antrean</h2>
        <div className="flex flex-col gap-2">
          {queueNames.map((name) => {
            const q = dashboard.queue[name]
            return (
              <div
                key={name}
                className="flex items-center justify-between rounded-lg border border-border p-3"
              >
                <span className="text-sm font-medium">{name}</span>
                <span className="text-xs text-muted-foreground">
                  {q.rq_error ? 'RQ tidak tersedia' : `RQ: ${q.rq_length} (${q.rq_failed} gagal)`} ·
                  TaskQueue: {q.task_queue_length}
                </span>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
