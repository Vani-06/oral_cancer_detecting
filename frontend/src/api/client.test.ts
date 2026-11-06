import { describe, expect, it } from 'vitest'

import { mockFetch, route } from '@/test/fetchMock'
import { ApiError, deleteRequest, getJson, postJson, resolveUrl, setToken } from './client'

describe('api client', () => {
  it('sends the stored bearer token', async () => {
    setToken('abc')
    const calls = mockFetch(route('GET', '/me', 200, { id: 1 }))
    await getJson('/me')
    expect(calls).toHaveLength(1)
    const init = (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0][1]
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer abc')
  })

  it('turns FastAPI validation errors into one readable message', async () => {
    mockFetch(
      route('POST', '/login', 422, {
        detail: [{ msg: 'field required', loc: ['body', 'email'] }, { msg: 'too short' }],
      }),
    )
    const error = await postJson('/login', {}).catch((cause: unknown) => cause)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(422)
    expect((error as ApiError).detail).toBe('field required; too short')
  })

  it('reports an unreachable server as a network error', async () => {
    mockFetch()
    ;(fetch as unknown as { mockRejectedValueOnce: (e: Error) => void }).mockRejectedValueOnce(
      new TypeError('Failed to fetch'),
    )
    const error = (await getJson('/me').catch((cause: unknown) => cause)) as ApiError
    expect(error.isNetworkError).toBe(true)
  })

  it('accepts an empty 204 response', async () => {
    mockFetch(route('DELETE', '/predictions/3', 204))
    await expect(deleteRequest('/predictions/3')).resolves.toBeUndefined()
  })

  it('resolves server-relative URLs against the API, leaving data URIs alone', () => {
    expect(resolveUrl('/reports/1')).toMatch(/^https?:\/\/.+\/reports\/1$/)
    expect(resolveUrl('data:image/png;base64,AA')).toBe('data:image/png;base64,AA')
  })
})
