/** Presentational only (FRONTEND_ARCHITECTURE.md §3.1) — sending is delegated via `onSend`. */
import { useState, type KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ComposerProps {
  disabled?: boolean
  onSend: (message: string) => void
}

export function Composer({ disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState('')

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex items-end gap-2 border-t border-border pt-4">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        rows={2}
        placeholder="Ketik pesan… (Enter untuk kirim, Shift+Enter baris baru)"
        className="flex-1 resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
      />
      <Button onClick={submit} disabled={disabled || !value.trim()} size="icon" aria-label="Kirim">
        <Send size={16} />
      </Button>
    </div>
  )
}
