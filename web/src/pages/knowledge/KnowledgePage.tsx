/**
 * Knowledge — wired to the real `api/routes/knowledge.py` (confirmed
 * choice: paste-text ingest, not file upload/OCR — that's a separate
 * scope decision for later). First real HTTP wiring of `rag/` (Tahap 5).
 */
import { useCallback, useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { DocumentList } from '@/components/knowledge/DocumentList'
import { knowledgeService } from '@/services/knowledgeService'
import { useNotificationStore } from '@/stores/notificationStore'
import type { KnowledgeDocument, KnowledgeHit } from '@/types/knowledge'

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [ingesting, setIngesting] = useState(false)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<KnowledgeHit[] | null>(null)
  const [searching, setSearching] = useState(false)
  const pushNotification = useNotificationStore((s) => s.push)

  const fetchDocuments = useCallback(() => knowledgeService.listDocuments(), [])

  useEffect(() => {
    fetchDocuments()
      .then((res) => setDocuments(res.documents))
      .finally(() => setLoading(false))
  }, [fetchDocuments])

  async function onIngest() {
    if (!title.trim() || !text.trim()) return
    setIngesting(true)
    try {
      const result = await knowledgeService.ingestDocument(title, text)
      setTitle('')
      setText('')
      const res = await fetchDocuments()
      setDocuments(res.documents)
      pushNotification({
        variant: 'success',
        message: `"${result.title}" diindeks (${result.chunks_indexed} bagian).`,
      })
    } catch (e) {
      pushNotification({
        variant: 'destructive',
        message: e instanceof Error ? e.message : 'Gagal mengindeks dokumen',
      })
    } finally {
      setIngesting(false)
    }
  }

  async function onDelete(id: string) {
    await knowledgeService.deleteDocument(id)
    const res = await fetchDocuments()
    setDocuments(res.documents)
  }

  async function onSearch() {
    if (!query.trim()) return
    setSearching(true)
    try {
      const res = await knowledgeService.search(query)
      setHits(res.hits)
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Knowledge</h1>
        <p className="text-sm text-muted-foreground">Sumber pengetahuan yang dapat dirujuk AI.</p>
      </div>

      <section className="flex flex-col gap-2 rounded-lg border border-border p-4">
        <h2 className="text-sm font-medium">Tambah sumber baru</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Judul"
          className="rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
        />
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder="Tempel teks di sini…"
          className="resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <Button
          size="sm"
          className="w-fit"
          onClick={onIngest}
          disabled={ingesting || !title.trim() || !text.trim()}
        >
          {ingesting ? 'Mengindeks…' : 'Indeks'}
        </Button>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Cari</h2>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onSearch()}
            placeholder="Cari dalam sumber pengetahuan…"
            className="flex-1 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
          />
          <Button
            size="icon"
            onClick={onSearch}
            disabled={searching || !query.trim()}
            aria-label="Cari"
          >
            <Search size={16} />
          </Button>
        </div>
        {hits && (
          <div className="flex flex-col gap-2">
            {hits.length === 0 ? (
              <p className="text-sm text-muted-foreground">Tidak ada hasil.</p>
            ) : (
              hits.map((hit) => (
                <div key={hit.entry_id} className="rounded-lg border border-border p-3 text-sm">
                  <p className="text-xs text-muted-foreground">Skor {hit.score.toFixed(2)}</p>
                  <p>{hit.text}</p>
                </div>
              ))
            )}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Semua Sumber</h2>
        {loading ? (
          <Skeleton className="h-14 w-full" />
        ) : (
          <DocumentList documents={documents} onDelete={onDelete} />
        )}
      </section>
    </div>
  )
}
