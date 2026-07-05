/** Real shapes returned by `api/routes/projects.py`. */
export interface ProjectSummary {
  id: string
  name: string
  description: string | null
  status: 'active' | 'archived'
  created_at: string
}

export interface ProjectMember {
  principal_key: string
  role: 'owner' | 'editor' | 'viewer'
  added_at: string
}

export interface ProjectDetail {
  id: string
  name: string
  description: string | null
  status: 'active' | 'archived'
  owner_key: string
  created_at: string
  updated_at: string
  your_role: 'owner' | 'editor' | 'viewer'
  members: ProjectMember[]
}
