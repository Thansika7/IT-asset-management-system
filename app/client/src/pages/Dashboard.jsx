import React from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import { R, NAV } from '@/lib/roles'
import { FileStack, MapPinned, PackageSearch, Wallet, ArrowRight, Laptop, Users, Layers } from 'lucide-react'

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const q = useQueries({
    queries: [
      {
        queryKey: ['requests', 'dash'],
        queryFn: () => apiFetch('/requests/'),
      },
      {
        queryKey: ['tracking', 'dash'],
        queryFn: () => apiFetch('/tracking/'),
      },
      {
        queryKey: ['stock', 'dash'],
        queryFn: () => apiFetch('/stock/'),
        enabled: NAV.stock(user.role),
      },
      {
        queryKey: ['finance', 'dash'],
        queryFn: () => apiFetch(`/accounts/summary${user.branch ? `?branch=${encodeURIComponent(user.branch)}` : ''}`),
        enabled: NAV.finance(user.role),
      },
    ],
  })

  const [reqQ, trkQ, stockQ, finQ] = q
  const requests = reqQ.data ?? []
  const tracking = trkQ.data ?? []
  const stock = stockQ.data ?? []
  const finance = finQ.data

  const openRequests = Array.isArray(requests)
    ? requests.filter((r) => !['COMPLETED', 'REJECTED'].includes(String(r.status))).length
    : 0

  const stats = [
    {
      label: 'Active requests',
      value: reqQ.isLoading ? '-' : openRequests,
      sub: `${Array.isArray(requests) ? requests.length : 0} total`,
      icon: FileStack,
      onClick: () => navigate('/requests'),
      show: true,
      accent: 'from-cyan-500/15 via-white to-white',
    },
    {
      label: 'Tracking rows',
      value: trkQ.isLoading ? '-' : tracking.length,
      sub: 'Your visible scope',
      icon: MapPinned,
      onClick: () => navigate('/tracking'),
      show: true,
      accent: 'from-emerald-500/15 via-white to-white',
    },
    {
      label: 'Catalog assets',
      value: stockQ.isLoading ? '-' : stock.length,
      sub: 'Stock records',
      icon: PackageSearch,
      onClick: () => navigate('/stock'),
      show: NAV.stock(user.role),
      accent: 'from-amber-500/15 via-white to-white',
    },
    {
      label: 'Recorded asset value',
      value:
        finQ.isLoading ? '-' : finance
          ? Number(finance.total_asset_value).toLocaleString(undefined, { maximumFractionDigits: 2 })
          : '-',
      sub: 'Same currency as stored costs',
      icon: Wallet,
      onClick: () => navigate('/finance'),
      show: NAV.finance(user.role),
      accent: 'from-indigo-500/15 via-white to-white',
    },
  ]

  const quick = [
    { title: 'My Assets', desc: 'Assignments tied to your profile.', to: '/my-assets', show: true, icon: Laptop },
    { title: 'Request something', desc: 'New, replace, or service workflows.', to: '/requests', show: true, icon: FileStack },
    { title: 'Live tracking', desc: 'Movement history you are allowed to see.', to: '/tracking', show: true, icon: MapPinned },
    { title: 'Inventory', desc: 'On-hand stock by catalog asset.', to: '/stock', show: NAV.stock(user.role), icon: PackageSearch },
    { title: 'Finance snapshot', desc: 'Totals and overhead.', to: '/finance', show: NAV.finance(user.role), icon: Wallet },
    { title: 'Team directory', desc: 'People in your org scope.', to: '/employees', show: NAV.employees(user.role), icon: Users },
    {
      title: 'Onboarding kits',
      desc: 'Preset bundles for new hires; use when registering employees.',
      to: '/onboarding-kits',
      show: NAV.onboardingKits(user.role),
      icon: Layers,
    },
  ].filter((x) => x.show)

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto space-y-10">
      <header className="space-y-3 motion-fade-up">
        <p className="text-sm font-medium text-slate-500">Overview</p>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
          Hello {user.name}
        </h1>
        <p className="text-slate-600 max-w-2xl text-sm sm:text-base leading-relaxed">
          This dashboard pulls live totals from the API for your role. Open sections from the sidebar for full workflows.
        </p>
      </header>

      <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {stats
          .filter((s) => s.show)
          .map(({ label, value, sub, icon: Icon, onClick, accent }, index) => (
            <button
              key={label}
              type="button"
              onClick={onClick}
              className={`text-left rounded-2xl border border-slate-200/80 bg-gradient-to-br ${accent} p-5 shadow-sm hover:shadow-xl hover:border-teal-400 group cursor-pointer hover-lift surface-sheen motion-fade-up ${index > 0 ? `motion-delay-${Math.min(index, 4)}` : ''}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
                  <p className="text-2xl font-bold text-slate-900 mt-2 tabular-nums">{value}</p>
                  <p className="text-xs text-slate-500 mt-1">{sub}</p>
                </div>
                <div className="rounded-xl bg-white/80 p-2.5 text-slate-600 group-hover:bg-teal-50 group-hover:text-teal-700 transition-colors motion-float-soft">
                  <Icon className="w-5 h-5" />
                </div>
              </div>
              <div className="mt-4 flex items-center text-xs font-semibold text-teal-600 opacity-0 group-hover:opacity-100 transition-opacity">
                Open <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </div>
            </button>
          ))}
      </section>

      <section className="motion-fade-up motion-delay-2">
        <h2 className="text-lg font-bold text-slate-900 mb-4">Shortcuts</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {quick.map(({ title, desc, to, icon: Icon }, index) => (
            <button
              key={to}
              type="button"
              onClick={() => navigate(to)}
              className={`flex gap-4 rounded-2xl border border-slate-200 bg-white/95 p-5 text-left shadow-sm hover:border-teal-400 hover:shadow-lg cursor-pointer group hover-lift surface-sheen motion-fade-up ${index > 0 ? `motion-delay-${Math.min(index, 4)}` : ''}`}
            >
              <div className="shrink-0 h-11 w-11 rounded-xl bg-gradient-to-br from-slate-100 via-white to-cyan-50 flex items-center justify-center text-slate-700 group-hover:text-cyan-700 transition-colors">
                <Icon className="w-5 h-5" />
              </div>
              <div>
                <p className="font-semibold text-slate-900">{title}</p>
                <p className="text-sm text-slate-600 mt-0.5">{desc}</p>
              </div>
            </button>
          ))}
        </div>
      </section>

      {user.role === R.EMPLOYEE ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white/70 p-6 text-sm text-slate-600 motion-fade-up motion-delay-3">
          <strong className="text-slate-800">Tip:</strong> raises and replacements start under Requests. Managers, HR, support, and admins each see different actions there based on the backend rules.
        </div>
      ) : null}
    </div>
  )
}
