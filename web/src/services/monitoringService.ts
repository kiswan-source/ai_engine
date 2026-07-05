/** Talks to `api/routes/monitoring.py` — `/api/v1/monitoring/{dashboard,alerts}`. */
import { apiClient } from './apiClient'
import type { MonitoringDashboard, MonitoringAlert } from '@/types/monitoring'

export const monitoringService = {
  getDashboard: () => apiClient.get<MonitoringDashboard>('/api/v1/monitoring/dashboard'),
  getAlerts: () => apiClient.get<{ alerts: MonitoringAlert[] }>('/api/v1/monitoring/alerts'),
}
