import { NavLink } from 'react-router-dom'

import { cn } from '@/lib/cn'

function DashboardIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M3 3h6v6H3V3zm8 0h6v4h-6V3zM3 11h6v6H3v-6zm8 2h6v4h-6v-4z" />
    </svg>
  )
}

function ScanIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M3 3h4v2H5v2H3V3zm10 0h4v4h-2V5h-2V3zM3 13h2v2h2v2H3v-4zm12 0h2v4h-4v-2h2v-2zM10 6a4 4 0 1 1 0 8 4 4 0 0 1 0-8z" />
    </svg>
  )
}

function HistoryIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M10 2a8 8 0 1 0 8 8 .75.75 0 0 0-1.5 0A6.5 6.5 0 1 1 10 3.5a.75.75 0 0 0 0-1.5zm.75 3.5a.75.75 0 0 0-1.5 0V10c0 .27.144.518.378.65l3 1.714a.75.75 0 1 0 .744-1.303l-2.622-1.498V5.5z"
        clipRule="evenodd"
      />
    </svg>
  )
}

function AccountIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M10 2a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm-7 15c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5v1H3v-1z" />
    </svg>
  )
}

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', Icon: DashboardIcon, end: true },
  { to: '/predict', label: 'New Analysis', Icon: ScanIcon, end: false },
  { to: '/history', label: 'History', Icon: HistoryIcon, end: false },
  { to: '/account', label: 'Account', Icon: AccountIcon, end: false },
]

/** Vertical navigation. Hidden below the md breakpoint -- see MobileNav. */
export function Sidebar() {
  return (
    <aside className="bg-surface border-surface-border hidden w-56 shrink-0 border-r md:block">
      <div className="border-surface-border flex h-14 items-center gap-2 border-b px-5">
        <span className="bg-brand-600 h-6 w-6 rounded" aria-hidden="true" />
        <span className="text-sm font-semibold text-slate-900">OralSentinel</span>
      </div>
      <nav className="flex flex-col gap-1 p-3" aria-label="Main">
        {NAV_ITEMS.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-slate-600 hover:bg-slate-100',
              )
            }
          >
            <span className="h-5 w-5">
              <Icon />
            </span>
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

/** Bottom navigation for small screens. */
export function MobileNav() {
  return (
    <nav
      className="bg-surface border-surface-border fixed inset-x-0 bottom-0 flex border-t md:hidden"
      aria-label="Main"
    >
      {NAV_ITEMS.map(({ to, label, Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              'flex flex-1 flex-col items-center gap-1 py-2 text-xs font-medium',
              isActive ? 'text-brand-700' : 'text-slate-500',
            )
          }
        >
          <span className="h-5 w-5">
            <Icon />
          </span>
          {label}
        </NavLink>
      ))}
    </nav>
  )
}
