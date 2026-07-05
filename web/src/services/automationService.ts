/** Talks to `api/routes/automation.py` — `/api/v1/automation/*`. */
import { apiClient } from './apiClient'
import type { ScheduledJob, ScheduledJobCreateRequest } from '@/types/automation'

export const automationService = {
  list: () => apiClient.get<{ jobs: ScheduledJob[] }>('/api/v1/automation/jobs'),
  create: (req: ScheduledJobCreateRequest) =>
    apiClient.post<ScheduledJob>('/api/v1/automation/jobs', req),
  setEnabled: (id: string, enabled: boolean) =>
    apiClient.patch<ScheduledJob>(`/api/v1/automation/jobs/${encodeURIComponent(id)}`, { enabled }),
  remove: (id: string) =>
    apiClient.delete<{ deleted: boolean }>(`/api/v1/automation/jobs/${encodeURIComponent(id)}`),
  runNow: (id: string) =>
    apiClient.post<ScheduledJob>(`/api/v1/automation/jobs/${encodeURIComponent(id)}/run-now`),
}
