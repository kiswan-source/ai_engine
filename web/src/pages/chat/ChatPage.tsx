/**
 * First fully-working Phase 1 feature (READY_FOR_IMPLEMENTATION.md §3 step
 * 4) — `chat.py` is the one stable, protected endpoint (Bab 45.1). Combines
 * chatStore + sessionStore + attachmentStore + notificationStore with
 * `chatService`, per FRONTEND_ARCHITECTURE.md §3.1 ("pages/* may combine
 * several stores and services; components/* may not").
 */
import { useCallback, useRef, useState } from 'react'
import { MessageList } from '@/components/chat/MessageList'
import { Composer } from '@/components/chat/Composer'
import { useChatStore } from '@/stores/chatStore'
import { useSessionStore } from '@/stores/sessionStore'
import { useAttachmentStore } from '@/stores/attachmentStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { streamChat } from '@/services/chatService'

export default function ChatPage() {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const addMessage = useChatStore((s) => s.addMessage)
  const appendToLastAssistant = useChatStore((s) => s.appendToLastAssistant)
  const setStreaming = useChatStore((s) => s.setStreaming)

  const conversationId = useSessionStore((s) => s.conversationId)
  const setConversationId = useSessionStore((s) => s.setConversationId)

  const addAttachment = useAttachmentStore((s) => s.add)
  const pushNotification = useNotificationStore((s) => s.push)

  const [toolActivity, setToolActivity] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const onSend = useCallback(
    async (text: string) => {
      addMessage({ id: crypto.randomUUID(), role: 'user', content: text })
      addMessage({ id: crypto.randomUUID(), role: 'assistant', content: '', pending: true })
      setStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        await streamChat({
          sessionId: conversationId,
          message: text,
          signal: controller.signal,
          onEvent: (event) => {
            switch (event.type) {
              case 'session':
                if (!conversationId) setConversationId(event.session_id)
                break
              case 'token':
                appendToLastAssistant(event.text)
                break
              case 'tool_start':
                setToolActivity(event.name)
                break
              case 'tool_result':
                setToolActivity(null)
                break
              case 'file':
                addAttachment({
                  filename: event.filename,
                  ftype: event.ftype,
                  size: event.size,
                  direction: 'generated',
                })
                break
              case 'error':
                pushNotification({ variant: 'destructive', message: event.message })
                break
              case 'done':
                setStreaming(false)
                setToolActivity(null)
                break
            }
          },
        })
      } catch (e) {
        pushNotification({
          variant: 'destructive',
          message: e instanceof Error ? e.message : 'Gagal terhubung ke server',
        })
        setStreaming(false)
      }
    },
    [
      conversationId,
      addMessage,
      appendToLastAssistant,
      setStreaming,
      setConversationId,
      addAttachment,
      pushNotification,
    ],
  )

  return (
    <div className="flex h-full flex-col">
      <MessageList messages={messages} />
      {toolActivity && (
        <p className="pb-2 text-xs text-muted-foreground">
          Menjalankan Alat Bantu: {toolActivity}…
        </p>
      )}
      <Composer disabled={isStreaming} onSend={onSend} />
    </div>
  )
}
