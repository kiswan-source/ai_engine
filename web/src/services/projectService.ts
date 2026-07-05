/** Talks to `api/routes/projects.py` — `/api/v1/projects/*`. */
import { apiClient } from './apiClient'
import type { ProjectSummary, ProjectDetail } from '@/types/project'

export const projectService = {
  list: () => apiClient.get<{ projects: ProjectSummary[] }>('/api/v1/projects'),
  create: (name: string, description?: string) =>
    apiClient.post<{ id: string; name: string; status: string }>('/api/v1/projects', {
      name,
      description,
    }),
  get: (id: string) => apiClient.get<ProjectDetail>(`/api/v1/projects/${encodeURIComponent(id)}`),
  update: (id: string, patch: { name?: string; description?: string; status?: string }) =>
    apiClient.patch<{ id: string; name: string; status: string }>(
      `/api/v1/projects/${encodeURIComponent(id)}`,
      patch,
    ),
  archive: (id: string) =>
    apiClient.delete<{ id: string; status: string }>(`/api/v1/projects/${encodeURIComponent(id)}`),
  addMember: (id: string, principalKey: string, role: 'owner' | 'editor' | 'viewer') =>
    apiClient.post<{ principal_key: string; role: string }>(
      `/api/v1/projects/${encodeURIComponent(id)}/members`,
      {
        principal_key: principalKey,
        role,
      },
    ),
  removeMember: (id: string, principalKey: string) =>
    apiClient.delete<{ removed: boolean }>(
      `/api/v1/projects/${encodeURIComponent(id)}/members/${encodeURIComponent(principalKey)}`,
    ),
}
