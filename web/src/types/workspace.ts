/** Real shapes returned by `api/routes/workspace.py` (Bab 69, ADR-0005, Tahap 19). */
export type WorkspaceStatus = 'Active' | 'Scanning' | 'Indexing' | 'Error'
export type WorkspaceSourceType = 'Local' | 'Network' | 'Server' | 'Upload'
export type WorkspaceFileCategory = 'document' | 'image' | 'gis' | 'other'

export interface WorkspaceFolder {
  id: string
  path: string
  source_type: WorkspaceSourceType
  alias: string | null
  registered_at: string
}

export interface Workspace {
  id: string
  project_id: string
  root_path: string | null
  status: WorkspaceStatus
  last_scan_at: string | null
  created_at: string
  updated_at: string
  folders: WorkspaceFolder[]
}

export interface WorkspaceFile {
  folder_id: string
  folder_alias: string | null
  relative_path: string
  category: WorkspaceFileCategory
  size_bytes: number
  source: 'workspace'
}

export interface WorkspaceTreeFolder {
  id: string
  alias: string | null
  path: string
  source_type: WorkspaceSourceType
  files: string[]
}

export interface WorkspaceScanResult {
  status: WorkspaceStatus
  last_scan_at: string
  document_count: number
  image_count: number
  gis_count: number
  other_count: number
  total_size_bytes: number
}

export interface WorkspaceIndexResult {
  status: WorkspaceStatus
  chunks_indexed: number
}

export interface WorkspaceStatusSnapshot {
  id: string
  status: WorkspaceStatus
  root_path: string | null
  last_scan_at: string | null
}
