import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { AuthProvider } from '@/context/AuthProvider'

/** Renders `element` at `path` inside the router and auth provider the app uses. */
export function renderAt(
  path: string,
  element: ReactElement,
  {
    pattern,
    state,
    extra = [],
  }: {
    pattern?: string
    state?: unknown
    extra?: Array<{ path: string; element: ReactElement }>
  } = {},
) {
  const [pathname, search] = path.split('?')
  return render(
    <MemoryRouter initialEntries={[{ pathname, search: search ? `?${search}` : '', state }]}>
      <AuthProvider>
        <Routes>
          <Route path={pattern ?? pathname} element={element} />
          {extra.map((route) => (
            <Route key={route.path} path={route.path} element={route.element} />
          ))}
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}
