import { useEffect, useState } from 'react'

import { getToken, USE_MOCKS } from '@/api/client'

/**
 * Loads an API image with the Authorization header and returns an object URL
 * for <img src>.
 *
 * Patient photos and heatmaps are only served to their owner, and a plain
 * <img src> cannot send a bearer token. Local blob:/data: URLs (previews and
 * mock fixtures) are returned unchanged. Returns undefined while loading or
 * if the image could not be fetched.
 */
export function useAuthorizedImage(url: string | null | undefined) {
  const passthrough = !url || USE_MOCKS || /^(blob:|data:)/.test(url)
  const [loaded, setLoaded] = useState<{ url: string; objectUrl: string }>()

  useEffect(() => {
    if (passthrough || !url) return

    let objectUrl: string | undefined
    const controller = new AbortController()

    fetch(url, {
      headers: { Authorization: `Bearer ${getToken() ?? ''}` },
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.blob() : undefined))
      .then((blob) => {
        if (!blob) return
        objectUrl = URL.createObjectURL(blob)
        setLoaded({ url, objectUrl })
      })
      .catch(() => {
        // Aborted on unmount, or a network failure: leave the image empty.
      })

    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [url, passthrough])

  if (passthrough) return url ?? undefined
  // Ignore a result that belongs to a previous url.
  return loaded?.url === url ? loaded.objectUrl : undefined
}
