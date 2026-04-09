import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, RefreshCw, Search, AlertTriangle } from 'lucide-react'
import Pagination from '@/components/Pagination'
import { apiFetch } from '@/lib/api'
import { useAuth } from '@/context/AuthContext'

export default function HealthAnalytics() {
  const { user } = useAuth()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [branch, setBranch] = useState(user?.branch || '')
  const [category, setCategory] = useState('')
  const [healthRange, setHealthRange] = useState('')
  const [criticalOnly, setCriticalOnly] = useState(false)
  const PAGE_SIZE = 12

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), per_page: String(PAGE_SIZE) })
    if (search.trim()) params.set('search', search.trim())
    if (branch) params.set('branch', branch)
    if (category) params.set('category', category)
    if (healthRange) params.set('health_range', healthRange)
    return params.toString()
  }, [page, search, branch, category, healthRange])

  const endpoint = criticalOnly ? '/assets/health/critical' : '/assets/health/report'

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['health-analytics', endpoint, queryString],
    queryFn: () => apiFetch(`${endpoint}?${queryString}`),
  })

  const { data: options = { branches: [], categories: [], health_ranges: [] } } = useQuery({
    queryKey: ['health-analytics-options'],
    queryFn: () => apiFetch('/assets/health/options'),
  })

  const items = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const summaryCards = data
    ? [
        { label: 'Assets in scope', value: data.asset_count },
        { label: 'Healthy', value: data.healthy_assets },
        { label: 'Warning', value: data.warning_assets },
        { label: 'Critical', value: data.critical_assets },
        { label: 'Replace now', value: data.replacement_candidates },
        { label: 'Showing page', value: `${data.page || page}/${totalPages}` },
      ]
    : []

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Activity className="w-7 h-7 text-teal-600" />
            Health analytics
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Hardware-only, instance-level health scoring with search, branch/category filters, and backend pagination.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-slate-900">
          <Search className="w-4 h-4 text-slate-500" />
          <h2 className="text-sm font-bold uppercase tracking-[0.16em]">Search and Filters</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <input
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Search instance ID, serial number, or asset name"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
          />
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={branch}
            onChange={(e) => {
              setBranch(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All branches</option>
            {options.branches.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All categories</option>
            {options.categories.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={healthRange}
            onChange={(e) => {
              setHealthRange(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All health ranges</option>
            {options.health_ranges.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" checked={criticalOnly} onChange={(e) => { setCriticalOnly(e.target.checked); setPage(1) }} />
            Critical only
          </label>
          <button
            type="button"
            className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em]"
            onClick={() => {
              setSearch('')
              setBranch(user?.branch || '')
              setCategory('')
              setHealthRange('')
              setCriticalOnly(false)
              setPage(1)
            }}
          >
            Reset
          </button>
        </div>
      </section>

      {isLoading ? (
        <div className="py-20 text-center text-slate-400 animate-pulse">Loading health analytics...</div>
      ) : isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">{error?.message}</div>
      ) : (
        <>
          <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {summaryCards.map(({ label, value }) => (
              <div key={label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
                <p className="mt-3 text-2xl font-bold text-slate-900 tabular-nums">{String(value)}</p>
              </div>
            ))}
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white overflow-hidden shadow-sm">
            <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex items-center justify-between gap-3">
              <h2 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-900">{criticalOnly ? 'Critical assets' : 'Health report'}</h2>
              <p className="text-xs text-slate-500">Hardware only</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1100px] text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-[0.16em] text-slate-500">
                  <tr>
                    <th className="px-4 py-3 text-left">Asset</th>
                    <th className="px-4 py-3 text-left">Instance</th>
                    <th className="px-4 py-3 text-left">Serial</th>
                    <th className="px-4 py-3 text-left">Branch</th>
                    <th className="px-4 py-3 text-left">Status</th>
                    <th className="px-4 py-3 text-left">Health</th>
                    <th className="px-4 py-3 text-left">Recommendation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((item) => (
                    <tr key={`${item.instance_id || item.asset_id}`} className="hover:bg-slate-50/70">
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900">{item.asset_name}</div>
                        <div className="text-xs text-slate-500 font-mono">{item.asset_id}</div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-700">{item.instance_id || '—'}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-700">{item.serial_number || '—'}</td>
                      <td className="px-4 py-3 text-slate-700">{item.branch || '—'}</td>
                      <td className="px-4 py-3 text-slate-700">{item.status || '—'}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-900">{item.health_score}</span>
                          <span className="text-xs uppercase rounded-md px-2 py-0.5 border border-slate-200 bg-slate-50 text-slate-600">{item.classification}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-xs font-semibold uppercase tracking-wide text-slate-700">{item.recommendation}</div>
                        <div className="text-xs text-slate-500 mt-1">{item.recommendation_reason}</div>
                      </td>
                    </tr>
                  ))}
                  {items.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-14 text-center text-slate-400">
                        No health records found.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={total} />
          </section>
        </>
      )}

      <div className="rounded-2xl border border-dashed border-slate-300 bg-white/70 p-4 text-xs text-slate-500 flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-amber-500" />
        Hardware-only health scoring excludes software, furniture, accessories, and network assets.
      </div>
    </div>
  )
}
