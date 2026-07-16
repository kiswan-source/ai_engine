/**
 * 11 Information Architecture areas → routes (AI_WORKSPACE_ARCHITECTURE.md
 * §2, FRONTEND_ARCHITECTURE.md §5), plus one Fase 9 addition (DCF v5 mandate
 * "Workspace Manager UI"): a top-level `/workspace` area — the mandate
 * explicitly asks for a new sidebar entry, so this is a deliberate 12th area,
 * not an oversight of the original 11. Distinct from `projects/:id/workspace`
 * (the older per-Project detail view, kept as-is for existing workflows):
 * `/workspace` is the new Cursor/VS Code-style entry point that doesn't
 * require picking a Project first. Lazy-loaded per page so new areas
 * (Phase 2–3) don't grow the initial bundle (Future Scalability,
 * AI_WORKSPACE_ARCHITECTURE.md §8).
 */
import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { WorkspaceLayout } from '@/components/layout/WorkspaceLayout'

const ChatPage = lazy(() => import('@/pages/chat/ChatPage'))
const ProjectsPage = lazy(() => import('@/pages/projects/ProjectsPage'))
const WorkspacePage = lazy(() => import('@/pages/projects/WorkspacePage'))
const WorkspaceManagerPage = lazy(() => import('@/pages/workspace/WorkspaceManagerPage'))
const FilesPage = lazy(() => import('@/pages/files/FilesPage'))
const KnowledgePage = lazy(() => import('@/pages/knowledge/KnowledgePage'))
const MemoryPage = lazy(() => import('@/pages/memory/MemoryPage'))
const WorkflowPage = lazy(() => import('@/pages/workflow/WorkflowPage'))
const ApprovalPage = lazy(() => import('@/pages/approval/ApprovalPage'))
const HistoryPage = lazy(() => import('@/pages/history/HistoryPage'))
const MonitoringPage = lazy(() => import('@/pages/monitoring/MonitoringPage'))
const SettingsPage = lazy(() => import('@/pages/settings/SettingsPage'))

function withSuspense(element: ReactNode) {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Memuat…</div>}>
      {element}
    </Suspense>
  )
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <WorkspaceLayout />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: 'chat', element: withSuspense(<ChatPage />) },
      { path: 'chat/:conversationId', element: withSuspense(<ChatPage />) },
      { path: 'projects', element: withSuspense(<ProjectsPage />) },
      { path: 'projects/:projectId', element: withSuspense(<ProjectsPage />) },
      { path: 'projects/:projectId/workspace', element: withSuspense(<WorkspacePage />) },
      { path: 'workspace', element: withSuspense(<WorkspaceManagerPage />) },
      { path: 'files', element: withSuspense(<FilesPage />) },
      { path: 'knowledge', element: withSuspense(<KnowledgePage />) },
      { path: 'memory', element: withSuspense(<MemoryPage />) },
      { path: 'workflow', element: withSuspense(<WorkflowPage />) },
      { path: 'workflow/:workflowId', element: withSuspense(<WorkflowPage />) },
      { path: 'approval', element: withSuspense(<ApprovalPage />) },
      { path: 'history', element: withSuspense(<HistoryPage />) },
      { path: 'monitoring', element: withSuspense(<MonitoringPage />) },
      { path: 'settings', element: withSuspense(<SettingsPage />) },
    ],
  },
])
