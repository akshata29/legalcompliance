import { Link, useLocation } from 'react-router-dom'
import { Scale, LayoutDashboard, FileText, History, Zap } from 'lucide-react'
import clsx from 'clsx'

const NAV = [
  { to: '/',         label: 'Dashboard',    icon: LayoutDashboard },
  { to: '/process',  label: 'Process Doc',  icon: FileText },
  { to: '/sessions', label: 'Sessions',     icon: History },
]

export default function Sidebar() {
  const { pathname } = useLocation()

  return (
    <aside className="w-64 shrink-0 flex flex-col bg-surface-800 border-r border-border min-h-screen">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-border">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary-500/20 text-primary-400">
          <Scale size={20} />
        </div>
        <div>
          <p className="text-sm font-semibold text-white leading-tight">LegalCompliance</p>
          <p className="text-[11px] text-gray-500">EU Securities</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ to, label, icon: Icon }) => {
          const active = pathname === to
          return (
            <Link
              key={to}
              to={to}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-150',
                active
                  ? 'bg-primary-500/15 text-primary-400'
                  : 'text-gray-400 hover:text-gray-100 hover:bg-surface-600'
              )}
            >
              <Icon size={17} />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Optimization indicator */}
      <div className="px-4 pb-5">
        <div className="rounded-lg bg-success/10 border border-success/20 p-3">
          <div className="flex items-center gap-2 mb-1">
            <Zap size={14} className="text-success-400" />
            <span className="text-xs font-semibold text-success-400">Optimization Ready</span>
          </div>
          <p className="text-[11px] text-gray-400 leading-relaxed">
            Toggle between Legacy and Optimized pipelines to compare processing performance.
          </p>
        </div>
      </div>
    </aside>
  )
}
