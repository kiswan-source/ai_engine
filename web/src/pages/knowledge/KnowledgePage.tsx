import { PhasePlaceholder } from '@/components/layout/PhasePlaceholder'

export default function KnowledgePage() {
  return (
    <PhasePlaceholder
      title="Knowledge"
      phase="Phase 2"
      reason="rag/ (Tahap 5) belum tersambung ke endpoint apapun — tidak ada cara ingest dokumen maupun list sumber via HTTP sama sekali; butuh desain produk (UX ingest) sebelum dibangun."
    />
  )
}
