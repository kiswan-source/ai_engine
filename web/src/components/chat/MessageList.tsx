/** Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — reads props, never calls services directly. */
import { cn } from '@/lib/utils'
import type { ChatMessage } from '@/types/chat'

interface MessageListProps {
  messages: ChatMessage[]
}

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Mulai percakapan baru — tanyakan apa saja.
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto py-4">
      {messages.map((m) => (
        <div key={m.id} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
          <div
            className={cn(
              'max-w-[75%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap',
              m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground',
              m.pending && 'text-muted-foreground italic',
            )}
          >
            {m.content || (m.pending ? 'Mengetik…' : '')}
          </div>
        </div>
      ))}
    </div>
  )
}
