/**
 * Talks to the real `files.py` router — registered with an empty prefix in
 * `api/main.py` (`app.include_router(files_router.router, prefix="")`), so
 * its routes are `/reports`, `/reports/{filename}`, `/upload`, `/uploads`,
 * not under `/api/v1/*` like the rest of the API.
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
  reportDownloadUrl: (filename: string) => `/reports/${encodeURIComponent(filename)}`,
  uploadFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient.post<{ filename: string; path: string; size: number; ext: string }>(
      '/upload',
      form,
    )
  },
}
