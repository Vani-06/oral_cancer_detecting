import type { ComponentPropsWithoutRef } from 'react'

import { useAuthorizedImage } from '@/hooks/useAuthorizedImage'
import { cn } from '@/lib/cn'

interface AuthorizedImageProps extends Omit<ComponentPropsWithoutRef<'img'>, 'src'> {
  src: string | null | undefined
}

/** An <img> for API-served patient images, which require the auth token. */
export function AuthorizedImage({ src, className, alt, ...props }: AuthorizedImageProps) {
  const objectUrl = useAuthorizedImage(src)

  if (!objectUrl) {
    return <div role="img" aria-label={alt} className={cn('bg-slate-100', className)} />
  }

  return <img src={objectUrl} alt={alt} className={className} {...props} />
}
