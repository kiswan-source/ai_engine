/** Global providers (FRONTEND_ARCHITECTURE.md §1) — currently just system-theme sync. */
import { useEffect, type ReactNode } from 'react'

function useSystemTheme() {
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = (isDark: boolean) => document.documentElement.classList.toggle('dark', isDark)
    apply(media.matches)
    const listener = (e: MediaQueryListEvent) => apply(e.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])
}

export function Providers({ children }: { children: ReactNode }) {
  useSystemTheme()
  return children
}
