/**
 * Navigation across the 11 Information Architecture areas
 * (AI_WORKSPACE_ARCHITECTURE.md §2). Icons per DESIGN_SYSTEM.md §6 — one
 * icon per concept, consistent everywhere.
 */
import { NavLink } from 'react-router-dom'
import {
  MessageSquare,
  FolderKanban,
  File,
  BookOpen,
  Brain,
  Workflow,
  CheckCircle2,
  History,
  Activity,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUiStore } from '@/stores/uiStore'

const NAV_ITEMS = [
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/projects', label: 'Projects', icon: FolderKanban },
  { to: '/files', label: 'Files', icon: File },
  { to: '/knowledge', label: 'Knowledge', icon: BookOpen },
  { to: '/memory', label: 'Memory', icon: Brain },
  { to: '/workflow', label: 'Workflow', icon: Workflow },
  { to: '/approval', label: 'Approval', icon: CheckCircle2 },
  { to: '/history', label: 'History', icon: History },
  { to: '/monitoring', label: 'Monitoring', icon: Activity },
  { to: '/settings', label: 'Settings', icon: Settings },
] as const

export function Sidebar() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)

  return (
    <aside
      className={cn(
        'flex h-full flex-col border-r border-border bg-card transition-[width]',
        sidebarOpen ? 'w-64' : 'w-16',
      )}
    >
      <div className="flex items-center justify-between px-4 py-4">
        {sidebarOpen && <span className="text-lg font-medium">AI Engine</span>}
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label={sidebarOpen ? 'Tutup sidebar' : 'Buka sidebar'}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        </button>
      </div>
      <nav className="flex flex-1 flex-col gap-1 px-2">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )
            }
          >
            <Icon size={18} className="shrink-0" />
            {sidebarOpen && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
