/**
 * Settings (dasar) — READY_FOR_IMPLEMENTATION.md §3 step 8.
 *
 * Plugin toggle (Bab 59) lives here rather than a new sidebar area —
 * AI_WORKSPACE_ARCHITECTURE.md §8: "Area Settings harus memiliki ruang untuk
 * mengaktifkan/menonaktifkan kapabilitas tambahan (integrasi baru) tanpa
 * perubahan navigasi inti."
 */
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useSettingsStore } from '@/stores/settingsStore'
import { chatService } from '@/services/chatService'
import { pluginService } from '@/services/pluginService'
import type { Plugin } from '@/types/plugin'

export default function SettingsPage() {
  const apiKey = useSettingsStore((s) => s.apiKey)
  const setApiKey = useSettingsStore((s) => s.setApiKey)
  const defaultModel = useSettingsStore((s) => s.defaultModel)
  const setDefaultModel = useSettingsStore((s) => s.setDefaultModel)

  const [models, setModels] = useState<string[]>([])
  const [keyDraft, setKeyDraft] = useState(apiKey)
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const [togglingName, setTogglingName] = useState<string | null>(null)

  useEffect(() => {
    chatService.listModels().then((res) => {
      setModels(res.available)
      if (!defaultModel) setDefaultModel(res.default)
    })
    // Only needs to run once on mount; defaultModel/setDefaultModel are stable store refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    pluginService.list().then((res) => setPlugins(res.plugins))
  }, [])

  async function onTogglePlugin(plugin: Plugin) {
    setTogglingName(plugin.name)
    try {
      await pluginService.setEnabled(plugin.name, !plugin.enabled)
      const res = await pluginService.list()
      setPlugins(res.plugins)
    } finally {
      setTogglingName(null)
    }
  }

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

      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium">Plugin</label>
        <p className="text-xs text-muted-foreground">
          Kapabilitas tambahan yang bisa dipanggil dari Chat/Workflow.
        </p>
        <div className="flex flex-col gap-2">
          {plugins.map((plugin) => (
            <div
              key={plugin.name}
              className="flex items-center justify-between gap-2 rounded-lg border border-border p-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium">{plugin.name}</p>
                  <Badge
                    variant="outline"
                    className={plugin.enabled ? 'text-success' : 'text-muted-foreground'}
                  >
                    {plugin.enabled ? 'Aktif' : 'Nonaktif'}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">{plugin.description}</p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onTogglePlugin(plugin)}
                disabled={togglingName === plugin.name}
              >
                {plugin.enabled ? 'Nonaktifkan' : 'Aktifkan'}
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
