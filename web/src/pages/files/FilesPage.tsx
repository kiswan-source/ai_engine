/**
 * Files — `files.py` is READY (Feature Readiness Matrix, IMPLEMENTATION_BLUEPRINT.md
 * §3); originally left as a Phase 2 placeholder purely because it wasn't in
 * Phase 1's declared scope, not because the backend was missing. Wired for
 * real now: `GET /reports`, `GET /uploads`, `POST /upload`.
 */
import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { FileList } from '@/components/files/FileList'
import { fileService, type ReportFile, type UploadedFile } from '@/services/fileService'
import { useNotificationStore } from '@/stores/notificationStore'

export default function FilesPage() {
  const [reports, setReports] = useState<ReportFile[]>([])
  const [uploads, setUploads] = useState<UploadedFile[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pushNotification = useNotificationStore((s) => s.push)

  // Pure fetch, no setState here — callers (the mount effect, and
  // onFileChosen after a successful upload) each apply the result
  // themselves, so the effect body stays a single inline .then()/.finally()
  // chain (react-hooks/set-state-in-effect flags setState reached through a
  // locally-defined async helper).
  const fetchAll = useCallback(async () => {
    const [reportsRes, uploadsRes] = await Promise.all([
      fileService.listReports(),
      fileService.listUploads(),
    ])
    return { reports: reportsRes.files, uploads: uploadsRes.files }
  }, [])

  useEffect(() => {
    fetchAll()
      .then(({ reports, uploads }) => {
        setReports(reports)
        setUploads(uploads)
      })
      .finally(() => setLoading(false))
  }, [fetchAll])

  async function onFileChosen(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploading(true)
    try {
      await fileService.uploadFile(file)
      const { reports, uploads } = await fetchAll()
      setReports(reports)
      setUploads(uploads)
      pushNotification({ variant: 'success', message: `${file.name} berhasil diunggah.` })
    } catch (err) {
      pushNotification({
        variant: 'destructive',
        message: err instanceof Error ? err.message : 'Gagal mengunggah berkas',
      })
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Files</h1>
          <p className="text-sm text-muted-foreground">Berkas yang diunggah dan dihasilkan AI.</p>
        </div>
        <input ref={fileInputRef} type="file" className="hidden" onChange={onFileChosen} />
        <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
          <Upload size={16} className="mr-2" />
          {uploading ? 'Mengunggah…' : 'Unggah'}
        </Button>
      </div>

      {loading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : (
        <>
          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-medium">Dihasilkan AI</h2>
            <FileList
              files={reports}
              emptyLabel="Belum ada berkas yang dihasilkan."
              hrefFor={fileService.reportDownloadUrl}
            />
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-medium">Diunggah</h2>
            <FileList files={uploads} emptyLabel="Belum ada berkas yang diunggah." />
          </section>
        </>
      )}
    </div>
  )
}
