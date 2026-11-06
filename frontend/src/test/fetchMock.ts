import { vi } from 'vitest'

export interface Call {
  method: string
  url: string
  body: unknown
}

type Handler = (call: Call) => { status?: number; body?: unknown } | undefined

/**
 * Replaces global fetch. Each request is recorded and answered by the first
 * handler that returns a response; unmatched requests get a 404.
 */
export function mockFetch(...handlers: Handler[]) {
  const calls: Call[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const raw = init.body
    let body: unknown = raw
    if (typeof raw === 'string') body = JSON.parse(raw)
    else if (raw instanceof FormData) body = Object.fromEntries(raw.entries())
    const call = { method: init.method ?? 'GET', url: String(input), body }
    calls.push(call)
    for (const handler of handlers) {
      const response = handler(call)
      if (response) {
        const status = response.status ?? 200
        return new Response(status === 204 ? null : JSON.stringify(response.body ?? {}), {
          status,
          headers: { 'Content-Type': 'application/json' },
        })
      }
    }
    return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

export const route =
  (method: string, path: string, status: number, body?: unknown): Handler =>
  (call) =>
    call.method === method && new URL(call.url).pathname === path ? { status, body } : undefined
