import React, { useMemo, useState } from 'react'
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  PackageSearch,
  FileStack,
  MapPinned,
  Users,
  Wallet,
  Laptop,
  Layers,
  GitBranch,
  Activity,
  LogOut,
  Menu,
  X,
  ChevronRight,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { NAV, labelForRole } from '@/lib/roles'

const navDef = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, show: NAV.dashboard },
  { to: '/my-assets', label: 'My assets', icon: Laptop, show: NAV.myAssets },
  { to: '/requests', label: 'Requests', icon: FileStack, show: NAV.requests },
  { to: '/stock', label: 'Inventory', icon: PackageSearch, show: NAV.stock },
  { to: '/asset-usage', label: 'Asset usage', icon: Activity, show: NAV.assetUsage },
  { to: '/tracking', label: 'Tracking', icon: MapPinned, show: NAV.tracking },
  { to: '/finance', label: 'Finance', icon: Wallet, show: NAV.finance },
  { to: '/employees', label: 'Team', icon: Users, show: NAV.employees },
  { to: '/onboarding-kits', label: 'Onboarding kits', icon: Layers, show: NAV.onboardingKits },
  { to: '/cmdb', label: 'CMDB', icon: GitBranch, show: NAV.cmdb },
]

export default function MainLayout() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const items = useMemo(
    () => navDef.filter((n) => n.show(user.role)),
    [user.role],
  )

  const Crumb = () => {
    const match = items.find((i) => i.to === location.pathname || (i.to !== '/' && location.pathname.startsWith(i.to)))
    const label = match?.label ?? 'Dashboard'
    return (
      <div className="lg:hidden flex items-center gap-2 text-sm text-slate-500 font-medium px-4 py-3 border-b border-slate-200/80 bg-white/80 backdrop-blur-sm motion-fade-in">
        <ChevronRight className="w-4 h-4 rotate-180 text-slate-400" />
        <span className="text-slate-800">{label}</span>
      </div>
    )
  }

  const NavBody = ({ onPick }) => (
    <>
      <div className="px-5 pt-8 pb-6 motion-fade-up">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-teal-400 to-cyan-600 shadow-lg shadow-teal-500/20 flex items-center justify-center text-white font-bold text-sm motion-glow">
            IT
          </div>
          <div>
            <p className="text-white font-semibold tracking-tight leading-tight">Asset Control</p>
            <p className="text-xs text-slate-400">IT operations hub</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 space-y-1 overflow-y-auto pb-6">
        {items.map(({ to, label, icon: Icon }, index) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            onClick={() => onPick?.()}
            className={({ isActive }) =>
              [
                'group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 hover:scale-[1.02] active:scale-95 cursor-pointer motion-fade-up',
                index === 0 ? '' : `motion-delay-${Math.min(index, 4)}`,
                isActive
                  ? 'bg-white/10 text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.08)]'
                  : 'text-slate-400 hover:text-white hover:bg-white/5',
              ].join(' ')
            }
          >
            <Icon className="w-[18px] h-[18px] opacity-90" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-white/10 motion-fade-up motion-delay-3">
        <div className="rounded-xl bg-white/5 p-3 mb-3 surface-sheen">
          <p className="text-xs text-slate-500 uppercase tracking-wider font-semibold mb-1">Signed in</p>
          <p className="text-sm text-white font-medium truncate" title={user.email}>
            {user.email}
          </p>
          <p className="text-xs text-teal-300/90 mt-1 font-medium">{labelForRole(user.role)}</p>
          {user.branch ? (
            <p className="text-[11px] text-slate-500 mt-1 truncate">Branch · {user.branch}</p>
          ) : null}
        </div>
        <div className="space-y-3">
          <button
            type="button"
            onClick={() => navigate('/change-password')}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 transition-all duration-200"
          >
            Change password
          </button>
          <button
            type="button"
            onClick={logout}
            className="w-full flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-medium text-rose-300 hover:bg-rose-500/10 hover:text-rose-200 hover:scale-[1.02] active:scale-95 transition-all duration-200 cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </div>
    </>
  )

  const navigate = useNavigate()

  return (
    <div className="flex h-[100dvh] bg-transparent text-slate-900 font-sans antialiased motion-fade-in">
      <aside className="hidden lg:flex w-64 shrink-0 flex-col bg-slate-900 border-r border-white/5 relative overflow-hidden">
        <div className="absolute inset-x-0 -top-10 h-40 bg-[radial-gradient(circle_at_top,_rgba(45,212,191,0.22),_transparent_68%)] pointer-events-none motion-float-soft" />
        <NavBody />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden motion-fade-in">
          <button type="button" className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" aria-label="Close menu" onClick={() => setMobileOpen(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-[min(100%,20rem)] bg-slate-900 flex flex-col shadow-2xl motion-fade-up">
            <div className="flex items-center justify-end p-3">
              <button type="button" className="p-2 rounded-lg text-slate-400 hover:text-white" onClick={() => setMobileOpen(false)}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <NavBody onPick={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="lg:hidden flex items-center justify-between px-4 py-3 bg-white/85 border-b border-slate-200 shadow-sm backdrop-blur-sm motion-fade-in">
          <button type="button" className="p-2 -ml-2 rounded-lg text-slate-600 hover:bg-slate-100" onClick={() => setMobileOpen(true)}>
            <Menu className="w-6 h-6" />
          </button>
          <span className="text-sm font-bold text-slate-800">Asset Control</span>
          <span className="w-10" />
        </header>
        <Crumb />
        <main className="flex-1 overflow-y-auto">
          <div className="min-h-full motion-fade-up">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
