import { PhasePlaceholder } from '@/components/layout/PhasePlaceholder'

export default function MemoryPage() {
  return (
    <PhasePlaceholder
      title="Memory"
      phase="Phase 2"
      reason="memory/ tiers (Tahap 3) tidak punya method enumerasi sesi/scope, dan core/chat/engine.py belum menulis ke memory/ sama sekali — gap integrasi backend, bukan sekadar API yang belum dibangun."
    />
  )
}
