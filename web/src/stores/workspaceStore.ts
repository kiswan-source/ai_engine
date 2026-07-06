/**
 * Project Workspace state (Bab 69.14, ADR-0005, Tahap 19). Deliberately thin
 * — same minimalism as `projectStore.ts`: `WorkspacePage.tsx` fetches and
 * holds its own loading/files/scan-result state locally; this store only
 * holds the current Workspace object for other components (e.g. a future
 * nav badge) to read without refetching.
 */
import { create } from 'zustand'
import type { Workspace } from '@/types/workspace'

interface WorkspaceState {
  current: Workspace | null
  setCurrent: (workspace: Workspace | null) => void
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  current: null,
  setCurrent: (current) => set({ current }),
}))
