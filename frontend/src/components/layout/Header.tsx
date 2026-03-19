import { Bell, Settings } from 'lucide-react'

interface HeaderProps {
  title: string
  subtitle?: string
}

export default function Header({ title, subtitle }: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-4 border-b border-border bg-surface-800/50 backdrop-blur-sm sticky top-0 z-10">
      <div>
        <h1 className="text-lg font-semibold text-white">{title}</h1>
        {subtitle && <p className="text-sm text-gray-400 mt-0.5">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">
        <button className="p-2 rounded-lg text-gray-400 hover:text-gray-200 hover:bg-surface-600 transition-colors">
          <Bell size={18} />
        </button>
        <button className="p-2 rounded-lg text-gray-400 hover:text-gray-200 hover:bg-surface-600 transition-colors">
          <Settings size={18} />
        </button>
      </div>
    </header>
  )
}
