import React, { useMemo, useState } from 'react'
import Pagination from '@/components/Pagination'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import { RefreshCw, Search } from 'lucide-react'
import AssetDetailPanel from '@/components/AssetDetailPanel'

const STATUS_OPTIONS = ['ACTIVE', 'ALLOCATED', 'IN_REPAIR', 'WARRANTY', 'RETIRED', 'LOST', 'DAMAGED', 'available', 'allocated', 'low_stock']
const SORT_OPTIONS = [
  { value: 'priority_cost', label: 'Priority monitoring' },
  { value: 'tco', label: 'Highest TCO' },
  { value: 'maintenance', label: 'Highest maintenance' },
  { value: 'repair', label: 'Highest repair cost' },
  { value: 'depreciation', label: 'Highest depreciation' },
  { value: 'health', label: 'Lowest health first' },
]

function formatCurrency(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function financeTone(item) {
  if (item.replacement_recommendation === 'REPLACE') return 'bg-rose-50 text-rose-700 border-rose-200'
  if (item.health_score <= 50) return 'bg-amber-50 text-amber-700 border-amber-200'
  return 'bg-emerald-50 text-emerald-700 border-emerald-200'
}

export default function Finance() {
  const { user } = useAuth()
  const [selectedAssetId, setSelectedAssetId] = useState(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15
  const initialFilters = {
    search: '',
    category: '',
    subCategory: '',
    branch: user.branch || '',
    status: '',
    recommendation: '',
    availableOnly: false,
    allocatedOnly: false,
    lowStockOnly: false,
    minTco: '',
    maxTco: '',
    minHealth: '',
    maxHealth: '',
    sortBy: 'priority_cost',
  }
  const [draftFilters, setDraftFilters] = useState(initialFilters)
  const [appliedFilters, setAppliedFilters] = useState(initialFilters)

  const queryString = useMemo(() => {
    const params = new URLSearchParams()
    if (appliedFilters.search.trim()) params.set('search', appliedFilters.search.trim())
    if (appliedFilters.category.trim()) params.set('category', appliedFilters.category.trim())
    if (appliedFilters.subCategory.trim()) params.set('sub_category', appliedFilters.subCategory.trim())
    if (appliedFilters.branch.trim()) params.set('branch', appliedFilters.branch.trim())
    if (appliedFilters.status) params.set('status', appliedFilters.status)
    if (appliedFilters.recommendation) params.set('recommendation', appliedFilters.recommendation)
    if (appliedFilters.availableOnly) params.set('available_only', 'true')
    if (appliedFilters.allocatedOnly) params.set('allocated_only', 'true')
    if (appliedFilters.lowStockOnly) params.set('low_stock_only', 'true')
    if (appliedFilters.minTco) params.set('min_tco', appliedFilters.minTco)
    if (appliedFilters.maxTco) params.set('max_tco', appliedFilters.maxTco)
    if (appliedFilters.minHealth) params.set('min_health_score', appliedFilters.minHealth)
    if (appliedFilters.maxHealth) params.set('max_health_score', appliedFilters.maxHealth)
    params.set('sort_by', appliedFilters.sortBy)
    return params.toString()
  }, [appliedFilters])

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['finance-report', queryString],
    queryFn: () => apiFetch(`/assets/finance/report${queryString ? `?${queryString}` : ''}`),
  })

  const allItems = data?.items || []
  const totalPages = Math.ceil(allItems.length / PAGE_SIZE)
  const pagedItems = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return allItems.slice(start, start + PAGE_SIZE)
  }, [allItems, page, PAGE_SIZE])

  const selectedFinanceAsset = useMemo(() => {
    return allItems.find((item) => item.asset_id === selectedAssetId) || null
  }, [allItems, selectedAssetId])

  const assetDetailQuery = useQuery({
    queryKey: ['asset-detail', selectedFinanceAsset?.asset_id],
    queryFn: () => apiFetch(`/assets/${selectedFinanceAsset.asset_id}/detail`),
    enabled: Boolean(selectedFinanceAsset?.asset_id),
  })

  const cards = data
    ? [
        { label: 'Tracked assets', value: data.asset_count, format: 'int' },
        { label: 'Purchase cost', value: data.total_purchase_cost, format: 'currency' },
        { label: 'Maintenance cost', value: data.total_maintenance_cost, format: 'currency' },
        { label: 'Repair cost', value: data.total_repair_cost, format: 'currency' },
        { label: 'Depreciation', value: data.total_depreciation, format: 'currency' },
        { label: 'Total ownership cost', value: data.total_cost_of_ownership, format: 'currency' },
      ]
    : []

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 motion-fade-up">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Finance</h1>
          <p className="text-sm text-slate-600 mt-1">Per-asset accounts monitoring with searchable cost, depreciation, health, and replacement signals.</p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm space-y-4 motion-fade-up motion-delay-1 surface-sheen">
        <div className="flex items-center gap-2 text-slate-900">
          <Search className="w-4 h-4 text-slate-500" />
          <h2 className="text-sm font-bold uppercase tracking-[0.16em]">Search and Filters</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Search asset, category, vendor, branch..." value={draftFilters.search} onChange={(e) => setDraftFilters((prev) => ({ ...prev, search: e.target.value }))} />
          <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Category" value={draftFilters.category} onChange={(e) => setDraftFilters((prev) => ({ ...prev, category: e.target.value }))} />
          <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Sub-category" value={draftFilters.subCategory} onChange={(e) => setDraftFilters((prev) => ({ ...prev, subCategory: e.target.value }))} />
          <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Branch" value={draftFilters.branch} onChange={(e) => setDraftFilters((prev) => ({ ...prev, branch: e.target.value }))} disabled={Boolean(user.branch && user.role === 'manager')} />
          <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={draftFilters.status} onChange={(e) => setDraftFilters((prev) => ({ ...prev, status: e.target.value }))}>
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={draftFilters.recommendation} onChange={(e) => setDraftFilters((prev) => ({ ...prev, recommendation: e.target.value }))}>
            <option value="">All recommendations</option>
            <option value="REPLACE">Replace</option>
            <option value="RETAIN">Retain</option>
          </select>
          <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={draftFilters.sortBy} onChange={(e) => setDraftFilters((prev) => ({ ...prev, sortBy: e.target.value }))}>
            {SORT_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <div className="grid grid-cols-2 gap-2">
            <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Min TCO" type="number" min="0" value={draftFilters.minTco} onChange={(e) => setDraftFilters((prev) => ({ ...prev, minTco: e.target.value }))} />
            <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Max TCO" type="number" min="0" value={draftFilters.maxTco} onChange={(e) => setDraftFilters((prev) => ({ ...prev, maxTco: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Min health" type="number" min="0" max="100" value={draftFilters.minHealth} onChange={(e) => setDraftFilters((prev) => ({ ...prev, minHealth: e.target.value }))} />
            <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Max health" type="number" min="0" max="100" value={draftFilters.maxHealth} onChange={(e) => setDraftFilters((prev) => ({ ...prev, maxHealth: e.target.value }))} />
          </div>
        </div>
        <div className="flex flex-wrap gap-3 text-sm text-slate-600">
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={draftFilters.availableOnly} onChange={(e) => setDraftFilters((prev) => ({ ...prev, availableOnly: e.target.checked }))} /> Available only</label>
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={draftFilters.allocatedOnly} onChange={(e) => setDraftFilters((prev) => ({ ...prev, allocatedOnly: e.target.checked }))} /> Allocated only</label>
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={draftFilters.lowStockOnly} onChange={(e) => setDraftFilters((prev) => ({ ...prev, lowStockOnly: e.target.checked }))} /> Low stock only</label>
          <button type="button" className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em]" onClick={() => { setAppliedFilters(draftFilters); setPage(1) }}>Apply filters</button>
          <button
            type="button"
            className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em]"
            onClick={() => {
              setDraftFilters(initialFilters)
              setAppliedFilters(initialFilters)
              setPage(1)
            }}
          >
            Clear
          </button>
        </div>
      </section>

      {isLoading ? (
        <div className="py-20 text-center text-slate-400 animate-pulse">Loading finance monitor...</div>
      ) : isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">{error?.message}</div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {cards.map(({ label, value, format }, index) => (
              <div key={label} className={`rounded-2xl border border-slate-200 bg-white p-6 shadow-sm motion-fade-up ${index > 0 ? `motion-delay-${Math.min(index, 4)}` : ''}`}>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
                <p className="text-2xl font-bold text-slate-900 mt-3 tabular-nums">
                  {format === 'currency' ? formatCurrency(value) : Number(value || 0).toLocaleString()}
                </p>
              </div>
            ))}
          </div>

          <section className="grid gap-6">
            <div className="rounded-3xl border border-slate-200 bg-white shadow-sm overflow-hidden motion-fade-up motion-delay-2">
              <div className="px-5 py-4 border-b border-slate-200 bg-slate-50">
                <h2 className="text-lg font-bold text-slate-900">Per-Asset Monitoring</h2>
                <p className="text-sm text-slate-600 mt-1">Click any asset row to inspect full commercial and operational details.</p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50 text-slate-500 uppercase text-[11px] tracking-[0.16em]">
                    <tr>
                      <th className="text-left px-4 py-3">Asset</th>
                      <th className="text-left px-4 py-3">Branch</th>
                      <th className="text-left px-4 py-3">Status</th>
                      <th className="text-left px-4 py-3">Health</th>
                      <th className="text-left px-4 py-3">Purchase</th>
                      <th className="text-left px-4 py-3">Maintenance</th>
                      <th className="text-left px-4 py-3">Repair</th>
                      <th className="text-left px-4 py-3">Depreciation</th>
                      <th className="text-left px-4 py-3">Book value</th>
                      <th className="text-left px-4 py-3">TCO</th>
                      <th className="text-left px-4 py-3">Recommendation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {pagedItems.length ? pagedItems.map((item) => (
                      <tr key={item.asset_id} className={`cursor-pointer hover:bg-slate-50 ${selectedFinanceAsset?.asset_id === item.asset_id ? 'bg-cyan-50/60' : ''}`} onClick={() => { setSelectedAssetId(item.asset_id); setDetailsOpen(true) }}>
                        <td className="px-4 py-4 align-top">
                          <div>
                            <p className="font-semibold text-slate-900">{item.asset_name}</p>
                            <p className="text-xs text-slate-500 mt-1">{item.asset_id} · {item.category || 'No category'} · {item.sub_category || 'No sub-category'}</p>
                            <p className="text-xs text-slate-500 mt-1">Qty {item.used}/{item.total_quantity} used · {item.unused} unused</p>
                          </div>
                        </td>
                        <td className="px-4 py-4 align-top text-slate-700">{item.branch || 'Unassigned'}</td>
                        <td className="px-4 py-4 align-top">
                          <div className="space-y-1">
                            <span className="inline-flex rounded-lg border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-700">{item.status}</span>
                            {item.low_stock ? <p className="text-xs font-medium text-amber-700">Low stock</p> : null}
                          </div>
                        </td>
                        <td className="px-4 py-4 align-top">
                          <div className={`inline-flex rounded-xl border px-3 py-2 text-xs font-semibold ${financeTone(item)}`}>{item.health_score}/100</div>
                        </td>
                        <td className="px-4 py-4 align-top tabular-nums">{formatCurrency(item.purchase_cost)}</td>
                        <td className="px-4 py-4 align-top tabular-nums">{formatCurrency(item.maintenance_cost)}</td>
                        <td className="px-4 py-4 align-top tabular-nums">{formatCurrency(item.repair_cost)}</td>
                        <td className="px-4 py-4 align-top tabular-nums">{formatCurrency(item.accumulated_depreciation)}</td>
                        <td className="px-4 py-4 align-top tabular-nums">{formatCurrency(item.book_value)}</td>
                        <td className="px-4 py-4 align-top tabular-nums font-semibold text-slate-900">{formatCurrency(item.total_cost_of_ownership)}</td>
                        <td className="px-4 py-4 align-top">
                          <div className="space-y-1 max-w-[220px]">
                            <span className={`inline-flex rounded-lg border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${item.replacement_recommendation === 'REPLACE' ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>{item.replacement_recommendation}</span>
                            <p className="text-xs text-slate-500 leading-5">{item.recommendation_reason}</p>
                          </div>
                        </td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan="11" className="px-4 py-12 text-center text-slate-500">No assets matched the current finance filters.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={allItems.length} />
            </div>
          </section>

          {detailsOpen && selectedFinanceAsset ? (
            <div className="fixed inset-0 z-[9999] overflow-y-auto bg-slate-900/70 backdrop-blur-sm" onClick={() => { setDetailsOpen(false); setSelectedAssetId(null) }}>
              <div className="mx-auto mt-10 mb-10 w-full max-w-6xl overflow-auto rounded-3xl bg-white shadow-2xl border border-slate-200" onClick={(event) => event.stopPropagation()}>
                <button
                  type="button"
                  className="absolute right-4 top-4 inline-flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200"
                  onClick={() => setDetailsOpen(false)}
                  aria-label="Close asset details"
                >
                  ×
                </button>
                <div className="p-6">
                  <AssetDetailPanel
                    asset={assetDetailQuery.data}
                    title="Selected Asset"
                    subtitle={assetDetailQuery.isLoading ? 'Loading selected asset details...' : 'Selected asset details.'}
                  />
                </div>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
