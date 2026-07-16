/** Talks to `api/routes/workspace.py` — `/api/v1/workspace/*`. */
import { apiClient } from './apiClient'
import type {
  BrowseFsResult,
  MyWorkspace,
  QuickConnectResult,
  Workspace,
  WorkspaceFolder,
  WorkspaceIndexResult,
  WorkspaceScanResult,
  WorkspaceStatusSnapshot,
} from '@/types/workspace'

export const workspaceService = {
  getByProject: (projectId: string) =>
    apiClient.get<Workspace>(`/api/v1/workspace?project_id=${encodeURIComponent(projectId)}`),
  create: (projectId: string) => apiClient.post<Workspace>('/api/v1/workspace', { project_id: projectId }),
  updateRootPath: (workspaceId: string, rootPath: string) =>
    apiClient.patch<Workspace>(`/api/v1/workspace/${encodeURIComponent(workspaceId)}`, { root_path: rootPath }),
  remove: (workspaceId: string) =>
    apiClient.delete<{ id: string; deleted: boolean }>(`/api/v1/workspace/${encodeURIComponent(workspaceId)}`),
  mount: (workspaceId: string, path: string, alias?: string) =>
    apiClient.post<WorkspaceFolder>(`/api/v1/workspace/${encodeURIComponent(workspaceId)}/mount`, {
      path,
      source_type: 'Local',
      alias,
    }),
  scan: (workspaceId: string) =>
    apiClient.post<WorkspaceScanResult>(`/api/v1/workspace/${encodeURIComponent(workspaceId)}/scan`),
  index: (workspaceId: string) =>
    apiClient.post<WorkspaceIndexResult>(`/api/v1/workspace/${encodeURIComponent(workspaceId)}/index`),
  files: (workspaceId: string) =>
    apiClient.get<{ files: import('@/types/workspace').WorkspaceFile[] }>(
      `/api/v1/workspace/${encodeURIComponent(workspaceId)}/files`,
    ),
  tree: (workspaceId: string) =>
    apiClient.get<{ folders: import('@/types/workspace').WorkspaceTreeFolder[] }>(
      `/api/v1/workspace/${encodeURIComponent(workspaceId)}/tree`,
    ),
  status: (workspaceId: string) =>
    apiClient.get<WorkspaceStatusSnapshot>(`/api/v1/workspace/${encodeURIComponent(workspaceId)}/status`),
  // Fase 9 (Workspace Manager UI) — in-app folder browser + one-call connect.
  browseFs: (path?: string) =>
    apiClient.get<BrowseFsResult>(
      path ? `/api/v1/workspace/browse-fs?path=${encodeURIComponent(path)}` : '/api/v1/workspace/browse-fs',
    ),
  quickConnect: (path: string, alias?: string) =>
    apiClient.post<QuickConnectResult>('/api/v1/workspace/quick-connect', { path, alias }),
  mine: () => apiClient.get<{ workspaces: MyWorkspace[] }>('/api/v1/workspace/mine'),
}
