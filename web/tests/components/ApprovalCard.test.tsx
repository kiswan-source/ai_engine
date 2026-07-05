import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApprovalCard } from '@/components/approval/ApprovalCard'
import type { ApprovalRequest } from '@/types/approval'

const approval: ApprovalRequest = {
  trace_id: 'abcd1234efgh',
  reason: 'Confidence di bawah ambang',
  requested_at: Date.now() / 1000,
  sla_seconds: 3600,
  decided: false,
  approved: null,
  decided_by: '',
  decision_reason: '',
  decided_at: null,
}

describe('ApprovalCard', () => {
  it('renders the reason and delegates decisions via callbacks', async () => {
    const onApprove = vi.fn()
    const onReject = vi.fn()
    render(<ApprovalCard approval={approval} onApprove={onApprove} onReject={onReject} />)

    expect(screen.getByText('Confidence di bawah ambang')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Setujui' }))
    expect(onApprove).toHaveBeenCalledOnce()

    await userEvent.click(screen.getByRole('button', { name: 'Tolak' }))
    expect(onReject).toHaveBeenCalledOnce()
  })

  it('disables both actions while a decision is in flight', () => {
    render(<ApprovalCard approval={approval} onApprove={vi.fn()} onReject={vi.fn()} deciding />)
    expect(screen.getByRole('button', { name: 'Setujui' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Tolak' })).toBeDisabled()
  })
})
