/**
 * Renders assistant message content as real Markdown (Fase 10 fix — the
 * chat system prompt (`prompts/chat/system_v1.md`) explicitly instructs the
 * model to "pakai heading, poin, dan tabel markdown", but `MessageList.tsx`
 * used to dump `content` as plain text with no parser at all: every
 * "### **Heading**", bullet, and markdown table showed up as literal raw
 * syntax in the bubble instead of being rendered. `remark-gfm` adds table/
 * strikethrough/task-list support (GFM) since the system prompt asks for
 * tables specifically. No `rehype-raw`/HTML pass-through on purpose — model
 * output is untrusted text, and react-markdown's default (Markdown syntax
 * only, no raw HTML execution) is what keeps this XSS-safe by construction.
 */
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils'

export function ChatMarkdown({ content }: { content: string }) {
  return (
    <div className="chat-markdown space-y-2 text-sm leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ ...p }) => <h3 className="mt-3 mb-1 text-base font-semibold" {...p} />,
          h2: ({ ...p }) => <h3 className="mt-3 mb-1 text-base font-semibold" {...p} />,
          h3: ({ ...p }) => <h3 className="mt-3 mb-1 text-sm font-semibold" {...p} />,
          h4: ({ ...p }) => <h4 className="mt-2 mb-1 text-sm font-semibold" {...p} />,
          p: ({ ...p }) => <p className="mb-2 last:mb-0" {...p} />,
          ul: ({ ...p }) => <ul className="mb-2 list-disc space-y-0.5 pl-5 last:mb-0" {...p} />,
          ol: ({ ...p }) => <ol className="mb-2 list-decimal space-y-0.5 pl-5 last:mb-0" {...p} />,
          li: ({ ...p }) => <li {...p} />,
          a: ({ ...p }) => (
            <a className="break-all text-primary underline underline-offset-2" target="_blank" rel="noreferrer" {...p} />
          ),
          blockquote: ({ ...p }) => (
            <blockquote className="border-l-2 border-border pl-3 text-muted-foreground" {...p} />
          ),
          code: ({ className, children, ...p }) => {
            const isBlock = /language-/.test(className ?? '')
            return isBlock ? (
              <code className={cn('font-mono text-xs', className)} {...p}>
                {children}
              </code>
            ) : (
              <code className="rounded bg-black/10 px-1 py-0.5 font-mono text-xs dark:bg-white/10" {...p}>
                {children}
              </code>
            )
          },
          pre: ({ ...p }) => (
            <pre className="mb-2 overflow-x-auto rounded-md bg-black/10 p-2 last:mb-0 dark:bg-white/10" {...p} />
          ),
          table: ({ ...p }) => (
            <div className="mb-2 overflow-x-auto last:mb-0">
              <table className="border-collapse text-xs" {...p} />
            </div>
          ),
          thead: ({ ...p }) => <thead className="border-b border-border font-medium" {...p} />,
          th: ({ ...p }) => <th className="px-2 py-1 text-left" {...p} />,
          td: ({ ...p }) => <td className="border-t border-border/50 px-2 py-1" {...p} />,
          hr: () => <hr className="my-2 border-border" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
