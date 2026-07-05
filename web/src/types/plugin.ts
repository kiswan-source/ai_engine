/** Real shape returned by `api/routes/plugins.py`. */
export interface Plugin {
  name: string
  version: string
  description: string
  permission_action: string
  enabled: boolean
}
