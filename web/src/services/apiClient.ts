/**
 * Sole HTTP exit point from the frontend (FRONTEND_ARCHITECTURE.md §6,
 * IMPLEMENTATION_BLUEPRINT.md §2.1) — every `*Service.ts` goes through this,
 * never `fetch`/`axios` directly.
 */
import { useSettingsStore } from '@/stores/settingsStore'

/** API_CONTRACT.md §5 / API_GUIDELINES.md §5 — standard error envelope. */
export interface ApiErrorResponse {
  success: false
  error_code: string
  message: string
  trace_id: string
  details: Record<string, unknown>
}

export class ApiError extends Error {
  errorCode: string
  traceId: string
  details: Record<string, unknown>

  constructor(body: ApiErrorResponse, status: number) {
    super(body.message || `Request failed (${status})`)
    this.name = 'ApiError'
    this.errorCode = body.error_code || 'UNKNOWN_ERROR'
    this.traceId = body.trace_id || ''
    this.details = body.details || {}
  }
}

function authHeaders(): HeadersInit {
  const apiKey = useSettingsStore.getState().apiKey
  return apiKey ? { 'X-API-Key': apiKey } : {}
}

async function parseErrorBody(res: Response): Promise<ApiErrorResponse> {
  try {
    const body = await res.json()
    if (body && typeof body === 'object' && 'message' in body) {
      return body as ApiErrorResponse
    }
    // Plain FastAPI HTTPException shape: {"detail": "..."}
    return {
      success: false,
      error_code: 'HTTP_ERROR',
      message: body?.detail || res.statusText,
      trace_id: '',
      details: {},
    }
  } catch {
    return {
      success: false,
      error_code: 'HTTP_ERROR',
      message: res.statusText,
      trace_id: '',
      details: {},
    }
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...authHeaders(),
      ...init.headers,
    },
  })
  if (!res.ok) {
    throw new ApiError(await parseErrorBody(res), res.status)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path, { method: 'GET' }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body instanceof FormData ? body : JSON.stringify(body ?? {}),
    }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  /** Raw fetch for endpoints the caller needs to read as a stream (SSE) rather than JSON. */
  raw: (path: string, init: RequestInit = {}) =>
    fetch(path, {
      ...init,
      headers: {
        ...(init.body && !(init.body instanceof FormData)
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...authHeaders(),
        ...init.headers,
      },
    }),
}
