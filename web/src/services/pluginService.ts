/** Talks to `api/routes/plugins.py` — `/api/v1/plugins/*`. */
import { apiClient } from './apiClient'
import type { Plugin } from '@/types/plugin'

export const pluginService = {
  list: () => apiClient.get<{ plugins: Plugin[] }>('/api/v1/plugins'),
  setEnabled: (name: string, enabled: boolean) =>
    apiClient.patch<Plugin>(`/api/v1/plugins/${encodeURIComponent(name)}`, { enabled }),
}
