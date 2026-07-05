/**
 * Project State (IMPLEMENTATION_BLUEPRINT.md §7, PROJECT_SPECIFICATION.md).
 * Phase 3 — no backend entity exists yet (Feature Readiness Matrix: NOT
 * IMPLEMENTED). Kept as an empty, optional store now so Session State
 * doesn't need reshaping later (§7.2 rule 5: Session State runs fine with
 * no Project State above it until Phase 3).
 */
import { create } from 'zustand'

interface ProjectState {
  activeProjectId: string | null
  setActiveProjectId: (id: string | null) => void
}

export const useProjectStore = create<ProjectState>((set) => ({
  activeProjectId: null,
  setActiveProjectId: (activeProjectId) => set({ activeProjectId }),
}))
