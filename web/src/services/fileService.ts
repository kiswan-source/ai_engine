/**
 * Talks to the real `files.py` router — registered with an empty prefix in
 * `api/main.py` (`app.include_router(files_router.router, prefix="")`), so
 * its routes are `/reports`, `/reports/{filename}`, `/upload`, `/uploads`,
 * not under `/api/v1/*` like the rest of the API.
 *
 * Tahap 25: every route now requires `Depends(get_current_principal)`, so a
 * plain `<a href="/reports/...">` (no way to attach `X-API-Key`) would 401
 * once `API_KEYS` is configured. `downloadReport` instead fetches through
 * `apiClient.raw()` (which attaches the header) and triggers the browser
 * download from the resulting blob — the standard authenticated-download
 * pattern for an SPA that has no cookie-based session.
 */
import { apiClient } from './apiClient'

export interface ReportFile {
  filename: string
  size: number
  ext: string
}

export interface UploadedFile {
  filename: string
  path: string
  size: number
}

export const fileService = {
  listReports: () => apiClient.get<{ files: ReportFile[]; count: number }>('/reports'),
  listUploads: () => apiClient.get<{ files: UploadedFile[] }>('/uploads'),
  downloadReport: async (filename: string) => {
    const res = await apiClient.raw(`/reports/${encodeURIComponent(filename)}`)
    if (!res.ok) {
      throw new Error(`Unduh gagal (${res.status})`)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    try {
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
    } finally {
      URL.revokeObjectURL(url)
    }
  },
  uploadFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient.post<{ filename: string; path: string; size: number; ext: string }>(
      '/upload',
      form,
    )
  },
}
