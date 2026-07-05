/** Real shape returned by `api/routes/automation.py`. */
export interface ScheduledJob {
  id: string
  name: string
  prompt: string
  roles: string[]
  mode: string
  interval_seconds: number
  enabled: boolean
  last_run_at: string | null
  last_status: 'success' | 'failed' | null
  last_result_summary: string | null
  next_run_at: string | null
  created_at: string
}

export interface ScheduledJobCreateRequest {
  name: string
  prompt: string
  roles: string[]
  mode?: string
  interval_seconds: number
}
