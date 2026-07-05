/** Root shell (FRONTEND_ARCHITECTURE.md §3): Sidebar + Header + routed page content. */
import { Outlet } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

export function WorkspaceLayout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto px-6 py-4">
          <Outlet />
        </main>
      </div>
      <Toaster />
    </div>
  )
}
