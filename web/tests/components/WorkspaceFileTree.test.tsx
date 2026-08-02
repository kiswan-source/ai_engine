import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WorkspaceFileTree } from '@/components/workspace/WorkspaceFileTree'
import { ApiError } from '@/services/apiClient'
import { workspaceService } from '@/services/workspaceService'
import { useNotificationStore } from '@/stores/notificationStore'

/** Minimal DataTransfer stand-in — jsdom doesn't implement the real thing,
 * but the component only calls setData/getData, so a small backing Map is
 * enough to round-trip the drag payload through dragStart -> drop exactly
 * like a real browser would. */
function makeDataTransfer() {
  const store = new Map<string, string>()
  return {
    setData: (format: string, value: string) => store.set(format, value),
    getData: (format: string) => store.get(format) ?? '',
    effectAllowed: 'none',
  } as unknown as DataTransfer
}

vi.mock('@/services/workspaceService', () => ({
  workspaceService: {
    tree: vi.fn(),
    moveFile: vi.fn(),
    copyFile: vi.fn(),
    deleteRequest: vi.fn(),
    deleteConfirm: vi.fn(),
  },
}))

const mockedTree = vi.mocked(workspaceService.tree)
const mockedMove = vi.mocked(workspaceService.moveFile)
const mockedCopy = vi.mocked(workspaceService.copyFile)
const mockedDeleteRequest = vi.mocked(workspaceService.deleteRequest)
const mockedDeleteConfirm = vi.mocked(workspaceService.deleteConfirm)

function treeResponse(files: string[]) {
  return {
    folders: [
      { id: 'folder-1', alias: 'Docs', path: '/srv/docs', source_type: 'Local' as const, files },
    ],
  }
}

afterEach(() => {
  // resetAllMocks (not restoreAllMocks) — clears queued mockResolvedValue*/
  // mockRejectedValueOnce* implementations between tests too, not just spy
  // call history; without it a persistent (non-Once) mockResolvedValue set
  // in one test silently leaked into the next test's mock queue.
  vi.resetAllMocks()
  // useNotificationStore is a real (unmocked) Zustand singleton — clear it
  // so one test's pushed notifications can't be mistaken for another's.
  useNotificationStore.setState({ items: [] })
})

describe('WorkspaceFileTree', () => {
  it('builds a nested tree from the flat relative_path list and expands directories', async () => {
    mockedTree.mockResolvedValue(treeResponse(['a.txt', 'sub/b.txt']))
    render(<WorkspaceFileTree workspaceId="ws-1" />)

    expect(await screen.findByText('a.txt')).toBeInTheDocument()
    expect(screen.getByText('sub')).toBeInTheDocument()
    // Nested file starts collapsed — only the directory name shows, not its child.
    expect(screen.queryByText('b.txt')).not.toBeInTheDocument()

    await userEvent.click(screen.getByText('sub'))
    expect(await screen.findByText('b.txt')).toBeInTheDocument()
  })

  it('renames a file via the context menu, calling moveFile with the new path', async () => {
    mockedTree.mockResolvedValue(treeResponse(['a.txt']))
    mockedMove.mockResolvedValue({ success: true, src: 'a.txt', dst: 'b.txt' })
    vi.spyOn(window, 'prompt').mockReturnValue('b.txt')
    render(<WorkspaceFileTree workspaceId="ws-1" />)

    const row = await screen.findByText('a.txt')
    await userEvent.pointer({ keys: '[MouseRight]', target: row })
    await userEvent.click(await screen.findByText('Rename'))

    await waitFor(() => {
      expect(mockedMove).toHaveBeenCalledWith('ws-1', 'folder-1', 'a.txt', 'b.txt', false)
    })
  })

  it('does not offer Delete for a directory node (server 400s on directory delete)', async () => {
    mockedTree.mockResolvedValue(treeResponse(['sub/b.txt']))
    render(<WorkspaceFileTree workspaceId="ws-1" />)

    const row = await screen.findByText('sub')
    await userEvent.pointer({ keys: '[MouseRight]', target: row })
    expect(await screen.findByText('Rename')).toBeInTheDocument()
    expect(screen.queryByText('Delete')).not.toBeInTheDocument()
  })

  it('runs the two-step delete flow: request opens a confirm dialog, confirm calls deleteConfirm', async () => {
    mockedTree.mockResolvedValue(treeResponse(['a.txt']))
    mockedDeleteRequest.mockResolvedValue({
      token: 'tok-123',
      relative_path: 'a.txt',
      size_bytes: 42,
      expires_at: Date.now() / 1000 + 300,
    })
    mockedDeleteConfirm.mockResolvedValue({ success: true, path: 'a.txt', deleted: true })
    render(<WorkspaceFileTree workspaceId="ws-1" />)

    const row = await screen.findByText('a.txt')
    await userEvent.pointer({ keys: '[MouseRight]', target: row })
    await userEvent.click(await screen.findByText('Delete'))

    await waitFor(() => expect(mockedDeleteRequest).toHaveBeenCalledWith('ws-1', 'folder-1', 'a.txt'))
    expect(await screen.findByText('Hapus file?')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Konfirmasi Hapus/ }))
    await waitFor(() => expect(mockedDeleteConfirm).toHaveBeenCalledWith('ws-1', 'folder-1', 'tok-123'))
  })

  it('retries with overwrite=true when the destination already exists and the user confirms', async () => {
    mockedTree.mockResolvedValue(treeResponse(['a.txt']))
    vi.spyOn(window, 'prompt').mockReturnValue('b.txt')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockedMove
      .mockRejectedValueOnce(
        new ApiError(
          { success: false, error_code: 'HTTP_ERROR', message: "'b.txt' sudah ada. Set overwrite=true untuk menimpanya.", trace_id: '', details: {} },
          400,
        ),
      )
      .mockResolvedValueOnce({ success: true, src: 'a.txt', dst: 'b.txt' })
    render(<WorkspaceFileTree workspaceId="ws-1" />)

    const row = await screen.findByText('a.txt')
    await userEvent.pointer({ keys: '[MouseRight]', target: row })
    await userEvent.click(await screen.findByText('Rename'))

    await waitFor(() => expect(mockedMove).toHaveBeenNthCalledWith(2, 'ws-1', 'folder-1', 'a.txt', 'b.txt', true))
  })

  it('copying via the context menu is scoped to the file\'s own folder id', async () => {
    mockedTree.mockResolvedValue({
      folders: [
        { id: 'folder-1', alias: 'Docs', path: '/srv/docs', source_type: 'Local', files: ['a.txt'] },
        { id: 'folder-2', alias: 'Other', path: '/srv/other', source_type: 'Local', files: ['c.txt'] },
      ],
    })
    mockedCopy.mockResolvedValue({ success: true, src: 'a.txt', dst: 'a-copy.txt' })
    vi.spyOn(window, 'prompt').mockReturnValue('a-copy.txt')
    render(<WorkspaceFileTree workspaceId="ws-1" />)

    const row = await screen.findByText('a.txt')
    await userEvent.pointer({ keys: '[MouseRight]', target: row })
    await userEvent.click(await screen.findByText('Copy'))

    await waitFor(() => {
      expect(mockedCopy).toHaveBeenCalledWith('ws-1', 'folder-1', 'a.txt', 'a-copy.txt', false)
    })
  })

  // Gate 2 finding (2026-08-01): the previous version of this file had a
  // test *titled* "never offers cross-folder moves" that never actually
  // simulated a drag/drop — it only exercised the context-menu Copy path,
  // which is scoped to the file's own folderId by construction and can't
  // exercise `onDropOnDir`'s cross-folder check at all. These two tests
  // drive the real dragstart/drop DOM events instead.
  it('drag-and-drop within the same registered WorkspaceFolder calls moveFile', async () => {
    mockedTree.mockResolvedValue({
      folders: [{ id: 'folder-1', alias: 'Docs', path: '/srv/docs', source_type: 'Local', files: ['a.txt', 'sub/b.txt'] }],
    })
    mockedMove.mockResolvedValue({ success: true, src: 'a.txt', dst: 'sub/a.txt' })
    render(<WorkspaceFileTree workspaceId="ws-1" />)

    const source = (await screen.findByText('a.txt')).closest('div')!
    const targetDir = (await screen.findByText('sub')).closest('div')!
    const dt = makeDataTransfer()

    fireEvent.dragStart(source, { dataTransfer: dt })
    fireEvent.drop(targetDir, { dataTransfer: dt })

    await waitFor(() => {
      expect(mockedMove).toHaveBeenCalledWith('ws-1', 'folder-1', 'a.txt', 'sub/a.txt', false)
    })
  })

  it('dropping onto a different registered WorkspaceFolder is rejected client-side without calling moveFile', async () => {
    mockedTree.mockResolvedValue({
      folders: [
        { id: 'folder-1', alias: 'Docs', path: '/srv/docs', source_type: 'Local', files: ['a.txt'] },
        { id: 'folder-2', alias: 'Other', path: '/srv/other', source_type: 'Local', files: ['c.txt'] },
      ],
    })
    render(<WorkspaceFileTree workspaceId="ws-1" />)

    const source = (await screen.findByText('a.txt')).closest('div')!
    const otherFolderRoot = (await screen.findByText('Other')).closest('div')!
    const dt = makeDataTransfer()

    fireEvent.dragStart(source, { dataTransfer: dt })
    fireEvent.drop(otherFolderRoot, { dataTransfer: dt })

    await waitFor(() => {
      expect(useNotificationStore.getState().items.some((n) => n.variant === 'warning')).toBe(true)
    })
    expect(mockedMove).not.toHaveBeenCalled()
    expect(mockedCopy).not.toHaveBeenCalled()
  })
})
