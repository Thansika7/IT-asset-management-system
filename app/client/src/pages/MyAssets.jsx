import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import { R } from '@/lib/roles'
import { Plus, AlertCircle } from 'lucide-react'
import Pagination from '@/components/Pagination'

function AdminAllocationForm({ onSuccess, adminId }) {
  const qc = useQueryClient()
  const [selectedAssetId, setSelectedAssetId] = useState('')
  const [allocationType, setAllocationType] = useState('PERMANENT')
  const [reason, setReason] = useState('')
  const [validationHint, setValidationHint] = useState('')

  const stockQuery = useQuery({
    queryKey: ['stock-for-allocation'],
    queryFn: () => apiFetch('/stock/'),
  })

  const allocateMut = useMutation({
    mutationFn: (body) =>
      apiFetch('/requests/allocate/direct', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setSelectedAssetId('')
      setAllocationType('PERMANENT')
      setReason('')
      qc.invalidateQueries({ queryKey: ['my-assets'] })
      onSuccess()
    },
  })

  const stockItems = stockQuery.data?.items || []
  const availableItems = stockItems

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!selectedAssetId) {
      setValidationHint('Please select an asset.')
      return
    }
    setValidationHint('')
    allocateMut.mutate({
      asset_id: selectedAssetId,
      employee_id: adminId,
      allocation_type: allocationType,
      reason: reason || 'Allocated to self by admin',
    })
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-slate-200 bg-white p-6 space-y-4 shadow-sm">
      <div>
        <h3 className="text-lg font-bold text-slate-900 mb-1 flex items-center gap-2">
          <Plus className="w-5 h-5 text-teal-600" />
          Allocate Asset to Myself
        </h3>
        <p className="text-sm text-slate-600">Quickly allocate an asset directly to yourself</p>
      </div>

      {validationHint ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 flex gap-2 text-sm text-amber-900">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>{validationHint}</div>
        </div>
      ) : null}

      {allocateMut.isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 flex gap-2 text-sm text-rose-800">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>{allocateMut.error?.message || 'Failed to allocate asset'}</div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-2">Asset</label>
          <select
            value={selectedAssetId}
            onChange={(e) => {
              setSelectedAssetId(e.target.value)
              if (e.target.value) setValidationHint('')
            }}
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            disabled={stockQuery.isLoading}
          >
            <option value="">Select an asset…</option>
            {availableItems.map((asset) => (
              <option key={asset.asset_id} value={asset.asset_id}>
                {asset.name} ({asset.unused} available)
              </option>
            ))}
          </select>
          {stockQuery.isError && <p className="text-xs text-rose-600 mt-1">{stockQuery.error?.message}</p>}
        </div>

        <div>
          <label className="block text-sm font-semibold text-slate-700 mb-2">Allocation Type</label>
          <select
            value={allocationType}
            onChange={(e) => setAllocationType(e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
          >
            <option value="PERMANENT">Permanent</option>
            <option value="TEMPORARY">Temporary</option>
          </select>
        </div>

        <div className="sm:col-span-2">
          <label className="block text-sm font-semibold text-slate-700 mb-2">Reason (optional)</label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g., Personal use, Backup device"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
        </div>
      </div>

      <div className="flex justify-end pt-2">
        <button
          type="submit"
          disabled={allocateMut.isPending || !selectedAssetId}
          className="rounded-lg bg-teal-600 text-white font-semibold px-4 py-2 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {allocateMut.isPending ? 'Allocating…' : 'Allocate to Myself'}
        </button>
      </div>
    </form>
  )
}

export default function MyAssets() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const empId = user.employeeId
  const [allocationSuccess, setAllocationSuccess] = useState(false)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [branchFilter, setBranchFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [page, setPage] = useState(1)
  const [historyPage, setHistoryPage] = useState(1)
  const PAGE_SIZE = 10

  const queryString = new URLSearchParams({
    page: String(page),
    per_page: String(PAGE_SIZE),
  })
  if (search.trim()) queryString.set('search', search.trim())
  if (statusFilter) queryString.set('status', statusFilter)
  if (branchFilter) queryString.set('branch', branchFilter)
  if (categoryFilter) queryString.set('category', categoryFilter)

  const historyQueryString = new URLSearchParams({
    page: String(historyPage),
    per_page: String(PAGE_SIZE),
  })

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['my-assets', empId, page, search, statusFilter, branchFilter, categoryFilter],
    queryFn: () => apiFetch(`/employees/${empId}/assets?${queryString.toString()}`),
    enabled: Boolean(empId),
  })

  const optionsQuery = useQuery({
    queryKey: ['my-assets-options', empId],
    queryFn: () => apiFetch(`/employees/${empId}/assets/options`),
    enabled: Boolean(empId),
  })

  const historyQuery = useQuery({
    queryKey: ['my-assets-history', empId, historyPage],
    queryFn: () => apiFetch(`/employees/${empId}/assets/history?${historyQueryString.toString()}`),
    enabled: Boolean(empId),
  })

  const ackMut = useMutation({
    mutationFn: (trackingId) => apiFetch(`/accounts/acknowledge/${encodeURIComponent(trackingId)}`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-assets', empId] }),
  })

  const rows = data?.items ?? []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const filterOptions = optionsQuery.data || { statuses: [], branches: [], categories: [] }
  const historyRows = historyQuery.data?.items || []
  const historyTotal = historyQuery.data?.total || 0
  const historyTotalPages = Math.max(1, Math.ceil(historyTotal / PAGE_SIZE))

  if (!empId) {
    return (
      <div className="p-8 max-w-2xl mx-auto">
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
          Your session token does not include an employee id. Sign out and sign in again so the server can issue an updated token.
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 sm:p-8 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">My assets</h1>
        <p className="text-sm text-slate-600 mt-1">
          {user.role === R.ADMIN
            ? 'Quickly allocate assets to yourself without creating a request.'
            : 'Confirm receipt of each assignment. This records your acknowledgment in the system ('}
          {user.role !== R.ADMIN && <code className="text-xs bg-slate-100 px-1 rounded">POST /accounts/acknowledge/…</code>}
          {user.role !== R.ADMIN && ').'}
        </p>
      </div>

      {user.role === R.ADMIN && (
        <>
          <AdminAllocationForm
            adminId={empId}
            onSuccess={() => {
              setAllocationSuccess(true)
              setTimeout(() => setAllocationSuccess(false), 3000)
            }}
          />
          {allocationSuccess && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
              ✓ Asset allocated successfully!
            </div>
          )}
        </>
      )}

      {isLoading ? (
        <div className="py-16 text-center text-slate-400 animate-pulse">Loading…</div>
      ) : isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">{error?.message}</div>
      ) : rows.length === 0 ? (
        <>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 grid grid-cols-1 md:grid-cols-4 gap-3">
            <input
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-2"
              placeholder="Search instance id, serial number, asset name"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
            <select className="rounded-lg border border-slate-200 px-3 py-2 text-sm" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}>
              <option value="">All statuses</option>
              {filterOptions.statuses.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="rounded-lg border border-slate-200 px-3 py-2 text-sm" value={branchFilter} onChange={(e) => { setBranchFilter(e.target.value); setPage(1) }}>
              <option value="">All branches</option>
              {filterOptions.branches.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="rounded-lg border border-slate-200 px-3 py-2 text-sm" value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}>
              <option value="">All categories</option>
              {filterOptions.categories.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>
          <p className="rounded-2xl border border-dashed border-slate-200 p-10 text-center text-slate-500 text-sm">No active assets assigned.</p>
        </>
      ) : (
        <>
          <div className="rounded-2xl border border-slate-200 bg-white p-4 grid grid-cols-1 md:grid-cols-5 gap-3">
            <input
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-2"
              placeholder="Search instance id, serial number, asset name"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
            <select className="rounded-lg border border-slate-200 px-3 py-2 text-sm" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}>
              <option value="">All statuses</option>
              {filterOptions.statuses.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="rounded-lg border border-slate-200 px-3 py-2 text-sm" value={branchFilter} onChange={(e) => { setBranchFilter(e.target.value); setPage(1) }}>
              <option value="">All branches</option>
              {filterOptions.branches.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="rounded-lg border border-slate-200 px-3 py-2 text-sm" value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}>
              <option value="">All categories</option>
              {filterOptions.categories.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>

          <p className="text-xs text-slate-500">
            Use <strong>Copy id</strong> if an admin needs the tracking id for a return-to-stock action.
          </p>
          <ul className="space-y-3">
            {rows.map((r) => (
              <li key={r.tracking_id} className="rounded-2xl border border-slate-200 bg-white p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 shadow-sm">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <p className="font-mono text-xs text-slate-500">{r.instance_id}</p>
                    {r.category && (
                      <span className="text-[10px] font-bold uppercase tracking-wider bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded border border-indigo-100">
                        {r.category}
                      </span>
                    )}
                    <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200">{r.status}</span>
                  </div>
                  
                  <p className="font-bold text-slate-900 text-lg leading-tight">
                    {r.brand ? `${r.brand} ` : ''}{r.asset_name || 'Unknown Asset'}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">{r.model || 'Model —'} · {r.branch || 'Branch —'} · Serial: {r.serial_number || '—'}</p>
                  
                  {r.assigned_date && (
                    <p className="text-xs text-slate-500 mt-1">
                      Assigned: {new Date(r.assigned_date).toLocaleDateString()}
                    </p>
                  )}

                  <div className="mt-3 flex items-center gap-2 bg-slate-50 w-fit px-2 py-1.5 rounded-lg border border-slate-100">
                    <span className="text-[11px] font-medium text-slate-500">Trk: <span className="font-mono text-slate-700">{r.tracking_id}</span></span>
                    <button
                      type="button"
                      className="text-[11px] font-semibold text-teal-600 hover:text-teal-800 hover:underline cursor-pointer transition-colors"
                      onClick={() => navigator.clipboard.writeText(r.tracking_id)}
                    >
                      Copy
                    </button>
                  </div>
                </div>
                <div className="flex flex-col sm:items-end gap-2">
                  <span
                    className={`text-xs font-bold uppercase px-2 py-1 rounded-lg self-start sm:self-end ${
                      r.is_acknowledged ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'
                    }`}
                  >
                    {r.is_acknowledged ? 'Acknowledged' : 'Pending acknowledgment'}
                  </span>
                  {!r.is_acknowledged ? (
                    <button
                      type="button"
                      disabled={ackMut.isPending}
                      onClick={() => ackMut.mutate(r.tracking_id)}
                      className="rounded-xl bg-slate-900 text-white text-sm font-semibold px-4 py-2 hover:bg-slate-800 disabled:opacity-50"
                    >
                      {ackMut.isPending ? 'Saving…' : 'I acknowledge receipt'}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={total} />

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
            <h3 className="text-lg font-bold text-slate-900">Asset History</h3>
            {historyQuery.isLoading ? (
              <p className="text-sm text-slate-400 animate-pulse">Loading history…</p>
            ) : historyRows.length === 0 ? (
              <p className="text-sm text-slate-500">No history records.</p>
            ) : (
              <div className="space-y-2">
                {historyRows.map((h) => (
                  <div key={h.tracking_id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                    <p className="text-sm font-semibold text-slate-900">{h.asset_name} <span className="font-mono text-xs text-slate-500">({h.instance_id})</span></p>
                    <p className="text-xs text-slate-600 mt-1">Assigned: {h.assigned_date ? new Date(h.assigned_date).toLocaleString() : '—'} · Returned: {h.returned_at ? new Date(h.returned_at).toLocaleString() : '—'}</p>
                    <p className="text-xs text-slate-600 mt-1">Repair: {h.repair_history ? 'Yes' : 'No'} · Replacement: {h.replacement_history ? 'Yes' : 'No'} · Previous assignment: {h.previous_assignment ? 'Yes' : 'No'}</p>
                  </div>
                ))}
              </div>
            )}
            <Pagination page={historyPage} totalPages={historyTotalPages} onPageChange={setHistoryPage} pageSize={PAGE_SIZE} total={historyTotal} />
          </div>
        </>
      )}
      {ackMut.isError ? <p className="text-sm text-rose-600">{ackMut.error?.message}</p> : null}
    </div>
  )
}
