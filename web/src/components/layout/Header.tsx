/** Session identity + notifications + quick Settings access (FRONTEND_ARCHITECTURE.md §3). */
import { Bell } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useNotificationStore } from '@/stores/notificationStore'
import { useSessionStore } from '@/stores/sessionStore'

export function Header() {
  const notifications = useNotificationStore((s) => s.items)
  const conversationId = useSessionStore((s) => s.conversationId)

  return (
    <header className="flex h-14 items-center justify-between border-b border-border px-6">
      <span className="text-sm text-muted-foreground">
        {conversationId ? `Percakapan ${conversationId.slice(0, 8)}` : 'Percakapan baru'}
      </span>
      <div className="flex items-center gap-4">
        <Link
          to="/settings"
          className="relative text-muted-foreground hover:text-foreground"
          aria-label="Notifikasi"
        >
          <Bell size={18} />
          {notifications.length > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] text-destructive-foreground">
              {notifications.length}
            </span>
          )}
        </Link>
      </div>
    </header>
  )
}
