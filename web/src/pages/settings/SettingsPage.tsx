/** Settings (dasar) — READY_FOR_IMPLEMENTATION.md §3 step 8. */
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useSettingsStore } from '@/stores/settingsStore'
import { chatService } from '@/services/chatService'

export default function SettingsPage() {
  const apiKey = useSettingsStore((s) => s.apiKey)
  const setApiKey = useSettingsStore((s) => s.setApiKey)
  const defaultModel = useSettingsStore((s) => s.defaultModel)
  const setDefaultModel = useSettingsStore((s) => s.setDefaultModel)

  const [models, setModels] = useState<string[]>([])
  const [keyDraft, setKeyDraft] = useState(apiKey)

  useEffect(() => {
    chatService.listModels().then((res) => {
      setModels(res.available)
      if (!defaultModel) setDefaultModel(res.default)
    })
    // Only needs to run once on mount; defaultModel/setDefaultModel are stable store refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex max-w-md flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">Preferensi akun dan konfigurasi workspace.</p>
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium" htmlFor="model-select">
          Model default
        </label>
        <select
          id="model-select"
          value={defaultModel ?? ''}
          onChange={(e) => setDefaultModel(e.target.value)}
          className="rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
        >
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium" htmlFor="api-key">
          API Key (Orchestrator RBAC)
        </label>
        <div className="flex gap-2">
          <input
            id="api-key"
            type="password"
            value={keyDraft}
            onChange={(e) => setKeyDraft(e.target.value)}
            placeholder="Kosongkan jika tidak diperlukan"
            className="flex-1 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
          />
          <Button size="sm" onClick={() => setApiKey(keyDraft)}>
            Simpan
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Dipakai untuk endpoint yang butuh otorisasi (mis. keputusan Approval).
        </p>
      </div>
    </div>
  )
}
