import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`
}

/** dataviz skill — stat-tile values are Sans semibold, auto-compact ($4.2M, 12.9K). */
export function formatUsd(value: number): string {
  if (value === 0) return '$0.00'
  if (value < 1) return `$${value.toFixed(4)}`
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatMs(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`
  return `${value.toFixed(0)} ms`
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

/** Automation (Bab 68 Prioritas 5) — "tiap 30 detik" / "tiap 2 jam" from a raw interval_seconds. */
export function formatInterval(seconds: number): string {
  if (seconds < 60) return `tiap ${seconds} detik`
  if (seconds < 3600) return `tiap ${Math.round(seconds / 60)} menit`
  return `tiap ${Math.round(seconds / 3600)} jam`
}

/** Vision (Bab 17.1 role) — reads a File as a `data:<mime>;base64,<data>` URI, matching `api/routes/orchestrator.py`'s `_parse_data_uri`. */
export function fileToDataUri(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}
