/** Settings State (IMPLEMENTATION_BLUEPRINT.md §7) — persisted preferences/feature flags. */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsState {
  apiKey: string
  defaultModel: string | null
  setApiKey: (key: string) => void
  setDefaultModel: (model: string | null) => void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      apiKey: '',
      defaultModel: null,
      setApiKey: (apiKey) => set({ apiKey }),
      setDefaultModel: (defaultModel) => set({ defaultModel }),
    }),
    { name: 'ai-engine-settings' },
  ),
)
