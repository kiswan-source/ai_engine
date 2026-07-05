/**
 * Status colors are reserved (good/warning/critical) and always ship with an
 * icon + label, never color alone (dataviz skill). Purely presentational —
 * the page classifies the raw backend string into a variant.
 */
import { CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export type StatusVariant = 'success' | 'warning' | 'destructive'

const ICONS = { success: CheckCircle2, warning: AlertTriangle, destructive: AlertCircle } as const
const TEXT_COLOR = {
  success: 'text-success',
  warning: 'text-warning',
  destructive: 'text-destructive',
} as const

export function StatusBadge({ variant, label }: { variant: StatusVariant; label: string }) {
  const Icon = ICONS[variant]
  return (
    <Badge variant="outline" className={cn('gap-1', TEXT_COLOR[variant])}>
      <Icon size={12} />
      {label}
    </Badge>
  )
}
