import { Button } from '@/components/ui/Button'
import { useAuth } from '@/hooks/useAuth'

export function Topbar() {
  const { user, logout } = useAuth()

  return (
    <header className="bg-surface border-surface-border flex h-14 shrink-0 items-center justify-between gap-4 border-b px-4 sm:px-6">
      <span className="text-sm font-semibold text-slate-900 md:hidden">
        OralSentinel
      </span>

      <div className="ml-auto flex items-center gap-3">
        {user && (
          <span className="hidden text-sm text-slate-600 sm:inline">
            {user.full_name}
            <span className="text-slate-400"> · {user.email}</span>
          </span>
        )}
        <Button variant="secondary" size="sm" onClick={logout}>
          Sign out
        </Button>
      </div>
    </header>
  )
}
