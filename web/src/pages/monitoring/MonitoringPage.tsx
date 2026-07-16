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
import { formatUsd, formatMs, formatPercent, formatBytes } from '@/lib/utils'

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

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Workspace</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Total Workspace" value={String(dashboard.workspace.total_workspaces)} />
          <StatTile label="Aktif" value={String(dashboard.workspace.active)} />
          <StatTile label="Dokumen" value={String(dashboard.workspace.document_count)} />
          <StatTile label="Gambar" value={String(dashboard.workspace.image_count)} />
          <StatTile label="File GIS" value={String(dashboard.workspace.gis_count)} />
          <StatTile label="Ukuran total" value={formatBytes(dashboard.workspace.total_size_bytes)} />
        </div>
        {dashboard.workspace.errors.length > 0 && (
          <div className="flex flex-col gap-1 rounded-lg border border-warning/50 bg-warning/10 p-3">
            {dashboard.workspace.errors.map((err) => (
              <p key={err} className="text-xs text-warning-foreground">
                {err}
              </p>
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Keamanan</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatTile label="Total kejadian" value={String(dashboard.security.total_security_events)} />
          {Object.entries(dashboard.security.by_type).map(([type, count]) => (
            <StatTile key={type} label={type} value={String(count)} />
          ))}
        </div>
        {dashboard.security.recent.length > 0 && (
          <div className="flex flex-col gap-1">
            {dashboard.security.recent
              .slice()
              .reverse()
              .map((entry, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg border border-border p-2 text-xs"
                >
                  <span className="font-medium">{entry.event_type}</span>
                  <span className="text-muted-foreground">
                    {entry.actor} · {new Date(entry.timestamp * 1000).toLocaleTimeString()}
                  </span>
                </div>
              ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Audit Trail</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <StatTile label="Total entri" value={String(dashboard.audit.total_entries)} />
          <StatTile label="Aktor unik" value={String(dashboard.audit.unique_actors)} />
        </div>
        {dashboard.audit.recent.length > 0 && (
          <div className="flex flex-col gap-1">
            {dashboard.audit.recent
              .slice()
              .reverse()
              .map((entry, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg border border-border p-2 text-xs"
                >
                  <span className="font-medium">{entry.event_type}</span>
                  <span className="text-muted-foreground">
                    {entry.actor} · {new Date(entry.timestamp * 1000).toLocaleTimeString()}
                  </span>
                </div>
              ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Peningkatan Berkelanjutan</h2>
          {dashboard.improvement && (
            <StatusBadge
              variant={dashboard.improvement.ledger_integrity_ok ? 'success' : 'destructive'}
              label={dashboard.improvement.ledger_integrity_ok ? 'Ledger utuh' : 'Ledger bermasalah'}
            />
          )}
        </div>

        {!dashboard.improvement ? (
          // Backend belum di-restart sejak Fase 7 di-deploy — respons API-nya
          // masih tidak punya key ini sama sekali. Tampilkan pesan yang jelas
          // alih-alih membiarkan halaman ini crash (ditemukan live: backend
          // lama + frontend baru ternyata kombinasi nyata yang terjadi saat
          // rebuild frontend mendahului restart backend, bukan skenario
          // hipotetis).
          <p className="rounded-lg border border-border p-3 text-xs text-muted-foreground">
            Data belum tersedia — backend perlu di-restart untuk memuat fitur ini.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <StatTile label="Total rekomendasi" value={String(dashboard.improvement.total_recommendations)} />
              <StatTile label="Diterapkan otomatis" value={String(dashboard.improvement.total_actions_applied)} />
              <StatTile label="Sudah ditinjau" value={String(dashboard.improvement.total_actions_reviewed)} />
            </div>

            {dashboard.improvement.pending_review.length > 0 && (
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-medium text-muted-foreground">Menunggu peninjauan</h3>
                {dashboard.improvement.pending_review.map((action) => (
                  <div
                    key={action.id}
                    className="flex items-center justify-between rounded-lg border border-border p-2 text-xs"
                  >
                    <span className="font-medium">
                      {action.setting}: {action.old_value} → {action.new_value}
                    </span>
                    <span className="text-muted-foreground">
                      Ditinjau setelah {new Date(action.review_after * 1000).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {dashboard.improvement.recent_recommendations.length > 0 && (
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-medium text-muted-foreground">Rekomendasi terbaru</h3>
                {dashboard.improvement.recent_recommendations
                  .slice()
                  .reverse()
                  .map((rec) => (
                    <div key={rec.id} className="flex flex-col gap-1 rounded-lg border border-border p-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{rec.category}</span>
                        <StatusBadge
                          variant={rec.severity === 'high' ? 'destructive' : rec.severity === 'medium' ? 'warning' : 'success'}
                          label={rec.severity}
                        />
                      </div>
                      <p className="text-muted-foreground">{rec.suggestion}</p>
                    </div>
                  ))}
              </div>
            )}

            {dashboard.improvement.recent_actions_reviewed.length > 0 && (
              <div className="flex flex-col gap-1">
                <h3 className="text-sm font-medium text-muted-foreground">Hasil peninjauan terbaru</h3>
                {dashboard.improvement.recent_actions_reviewed
                  .slice()
                  .reverse()
                  .map((action) => (
                    <div
                      key={action.id}
                      className="flex items-center justify-between rounded-lg border border-border p-2 text-xs"
                    >
                      <span className="font-medium">
                        {action.setting}: {action.old_value} → {action.new_value}
                      </span>
                      <StatusBadge
                        variant={action.outcome === 'kept' ? 'success' : 'warning'}
                        label={action.outcome ?? 'unknown'}
                      />
                    </div>
                  ))}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
