/**
 * History (READY_FOR_IMPLEMENTATION.md §3 step 7) — no dedicated History
 * API exists yet (Feature Readiness Matrix: REQUIRES ADAPTER), so this reads
 * `chat.py`'s own session list as the closest real substitute for now.
 */
import { useEffect } from 'react'
import { MessageSquare } from 'lucide-react'
import { useHistoryStore } from '@/stores/historyStore'
import { useSessionStore } from '@/stores/sessionStore'
import { chatService } from '@/services/chatService'
import { Skeleton } from '@/components/ui/skeleton'

export default function HistoryPage() {
  const items = useHistoryStore((s) => s.items)
  const loading = useHistoryStore((s) => s.loading)
  const setItems = useHistoryStore((s) => s.setItems)
  const setLoading = useHistoryStore((s) => s.setLoading)
  const setConversationId = useSessionStore((s) => s.setConversationId)

  useEffect(() => {
    setLoading(true)
    chatService
      .listSessions()
      .then((res) => setItems(res.sessions))
      .finally(() => setLoading(false))
  }, [setItems, setLoading])

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">History</h1>
        <p className="text-sm text-muted-foreground">
          Percakapan dan pekerjaan lampau — lanjutkan kapan saja.
        </p>
      </div>

      {loading && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      {!loading && items.length === 0 && (
        <p className="text-sm text-muted-foreground">Belum ada riwayat percakapan.</p>
      )}

      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setConversationId(item.id)}
            className="flex items-center gap-3 rounded-lg border border-border p-3 text-left hover:bg-accent"
          >
            <MessageSquare size={18} className="shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{item.title}</p>
              <p className="text-xs text-muted-foreground">{item.message_count} pesan</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
