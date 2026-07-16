import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatMarkdown } from '@/components/chat/ChatMarkdown'

describe('ChatMarkdown', () => {
  it('renders a heading combined with bold as real elements, not literal "### **" syntax', () => {
    const { container } = render(<ChatMarkdown content={'### **Ringkasan**\n\nIsi laporan.'} />)

    expect(container.textContent).not.toContain('###')
    expect(container.textContent).not.toContain('**')
    expect(screen.getByRole('heading', { name: 'Ringkasan' })).toBeInTheDocument()
    expect(container.querySelector('strong')?.textContent).toBe('Ringkasan')
  })

  it('renders GFM tables (the system prompt explicitly asks the model for markdown tables)', () => {
    const table = '| Nama | Luas (Ha) |\n| --- | --- |\n| Blok A | 11.35 |'
    render(<ChatMarkdown content={table} />)

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('Blok A')).toBeInTheDocument()
    expect(screen.getByText('11.35')).toBeInTheDocument()
  })

  it('renders bullet lists as real list items, not literal "- " text', () => {
    const { container } = render(<ChatMarkdown content={'- Poin satu\n- Poin dua'} />)

    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(container.textContent).not.toContain('- Poin')
  })

  it('never passes raw HTML through (model output is untrusted text)', () => {
    const { container } = render(<ChatMarkdown content={'<script>window.__pwned = true</script>'} />)

    expect(container.querySelector('script')).toBeNull()
  })
})
