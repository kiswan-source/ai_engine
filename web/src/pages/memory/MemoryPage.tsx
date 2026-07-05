/**
 * Memory — wired to the real `api/routes/memory.py` (confirmed choice: wire
 * as-is rather than wait for a ChatEngine↔memory/ integration). Will show
 * empty tiers for any real chat session_id today — `core/chat/engine.py`
 * never writes to `memory/` (docs/PROGRESS.md Tahap 12) — the banner below
 * says so explicitly rather than looking like a bug.
 */
import { useCallback, useEffect, useState } from 'react'
import { AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { KeyValueList } from '@/components/memory/KeyValueList'
import { memoryService } from '@/services/memoryService'
import { useSessionStore } from '@/stores/sessionStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type { SessionMemory } from '@/types/memory'

export default function MemoryPage() {
  const activeConversationId = useSessionStore((s) => s.conversationId)
  const [sessionId, setSessionId] = useState(activeConversationId ?? '')
  const [memory, setMemory] = useState<SessionMemory | null>(null)
  const [loading, setLoading] = useState(false)
  const pushNotification = useNotificationStore((s) => s.push)

  const fetchMemory = useCallback((id: string) => memoryService.getSessionMemory(id), [])

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    // The whole thing is one .then()-chain reached directly from the effect
    // body (rather than `setLoading(true)` as a bare leading statement) —
    // react-hooks/set-state-in-effect only recognizes setState calls inside
    // a .then()/.catch()/.finally() callback (see FilesPage/MonitoringPage
    // for the same fix).
    Promise.resolve()
      .then(() => {
        if (!cancelled) setLoading(true)
        return fetchMemory(sessionId)
      })
      .then((data) => {
        if (!cancelled) setMemory(data)
      })
      .catch(() => {
        // Session lookup failure — leave previous memory state as-is.
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, fetchMemory])

  async function reload() {
    if (!sessionId) return
    setMemory(await fetchMemory(sessionId))
  }

  async function onForgetWorking(key: string) {
    await memoryService.forgetWorking(sessionId, key)
    await reload()
  }

  async function onForgetLongTerm(key: string) {
    await memoryService.forgetLongTerm(sessionId, key)
    await reload()
  }

  async function onClearConversation() {
    await memoryService.clearConversation(sessionId)
    await reload()
    pushNotification({ variant: 'success', message: 'Riwayat percakapan untuk sesi ini dihapus.' })
  }

  async function onClearSummary() {
    await memoryService.clearSummary(sessionId)
    await reload()
  }

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Memory</h1>
        <p className="text-sm text-muted-foreground">Apa yang diingat sistem tentang sesi Anda.</p>
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-warning/50 bg-warning/10 p-3 text-sm">
        <AlertCircle size={16} className="mt-0.5 shrink-0 text-warning" />
        <p className="text-warning-foreground">
          Percakapan chat saat ini belum menulis ke sistem memori — bagian ini akan tampak kosong
          untuk sesi mana pun sampai integrasi tersebut dibangun. Ini gap backend yang diketahui,
          bukan halaman yang rusak.
        </p>
      </div>

      <div className="flex gap-2">
        <input
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          placeholder="session_id"
          className="flex-1 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
        />
      </div>

      {loading && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      {!loading && memory && (
        <>
          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-medium">Working Memory</h2>
            <KeyValueList
              entries={memory.working}
              emptyLabel="Kosong."
              onForget={onForgetWorking}
            />
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-medium">Long-Term Memory</h2>
            <KeyValueList
              entries={memory.long_term}
              emptyLabel="Kosong."
              onForget={onForgetLongTerm}
            />
          </section>

          <section className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium">Ringkasan Percakapan</h2>
              {memory.summary && (
                <Button size="sm" variant="outline" onClick={onClearSummary}>
                  Hapus
                </Button>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              {memory.summary ?? 'Belum ada ringkasan.'}
            </p>
          </section>

          <section className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium">Riwayat Percakapan</h2>
              {memory.conversation_history.length > 0 && (
                <Button size="sm" variant="outline" onClick={onClearConversation}>
                  Hapus Semua
                </Button>
              )}
            </div>
            {memory.conversation_history.length === 0 ? (
              <p className="text-sm text-muted-foreground">Kosong.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {memory.conversation_history.map((turn, i) => (
                  <div key={i} className="rounded-lg border border-border p-3 text-sm">
                    <span className="font-medium capitalize">{turn.role}: </span>
                    {turn.content}
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
