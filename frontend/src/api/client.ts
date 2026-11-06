/**
 * Low-level HTTP client.
 *
 * Every network call in the app goes through this module. Nothing else may
 * call `fetch` directly -- that rule is what keeps the mock/real switch to a
 * single env flag.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** When true, the api/* modules serve fixtures instead of calling the backend. */
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

const TOKEN_STORAGE_KEY = 'ocd.access_token'

/**
 * A failed request, normalised.
 *
 * `detail` is always a human-readable string, whatever shape the backend used
 * -- FastAPI sends `{detail: "..."}` for HTTPException (see the 400 raised in
 * backend/app/routers/prediction.py) but `{detail: [{msg, loc}, ...]}` for
 * request validation failures.
 */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  /** True when the request never reached the server. */
  get isNetworkError(): boolean {
    return this.status === 0
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}

/**
 * Turn a server-relative path into an absolute URL.
 *
 * The API hands back relative paths (`heatmap_url: "/uploads/heatmaps/1.png"`),
 * which would otherwise resolve against the Vite dev origin rather than the
 * backend. Absolute URLs and data URIs pass through untouched, so this is safe
 * to call on mock values too.
 */
export function resolveUrl(path: string): string {
  if (/^(https?:|data:|blob:)/.test(path)) return path
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

interface ErrorPayload {
  detail?: unknown
}

function extractDetail(payload: unknown, fallback: string): string {
  if (typeof payload !== 'object' || payload === null) return fallback

  const { detail } = payload as ErrorPayload
  if (typeof detail === 'string') return detail

  // FastAPI request-validation shape: a list of {loc, msg, type}.
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        typeof item === 'object' && item !== null && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : null,
      )
      .filter((msg): msg is string => msg !== null)

    if (messages.length > 0) return messages.join('; ')
  }

  return fallback
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(resolveUrl(path), { ...init, headers })
  } catch {
    throw new ApiError(
      0,
      `Could not reach the server at ${API_BASE_URL}. Is the backend running?`,
    )
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(
      response.status,
      extractDetail(payload, `Request failed with status ${response.status}.`),
    )
  }

  if (response.status === 204) return undefined as T

  return (await response.json()) as T
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/**
 * POST multipart/form-data.
 *
 * Deliberately does not set Content-Type: the browser must generate it so the
 * multipart boundary is included, otherwise FastAPI cannot parse the body.
 */
export function postForm<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', body: form })
}

export function patchJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteRequest(path: string): Promise<void> {
  return request<void>(path, { method: 'DELETE' })
}
