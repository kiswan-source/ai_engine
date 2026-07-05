/**
 * Headline number, one job (dataviz skill — "a handful of headline numbers"
 * → a KPI row of stat tiles, not a chart). Label sentence case, no trailing
 * colon; value in the default proportional sans, semibold.
 */
export function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  )
}
