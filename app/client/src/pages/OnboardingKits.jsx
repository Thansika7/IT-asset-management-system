import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import Pagination from '@/components/Pagination'
import { canManageOnboardingKits, labelForRole } from '@/lib/roles'
import { useAuth } from '@/context/AuthContext'
import { RefreshCw, Trash2, Plus } from 'lucide-react'
import ConfirmDialog from '@/components/ConfirmDialog'

export default function OnboardingKits() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const canEdit = canManageOnboardingKits(user.role)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [targetRoleFilter, setTargetRoleFilter] = useState('')
  const [branchFilter, setBranchFilter] = useState('')
  const PAGE_SIZE = 10

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), per_page: String(PAGE_SIZE) })
    if (search.trim()) params.set('search', search.trim())
    if (targetRoleFilter) params.set('target_role', targetRoleFilter)
    if (branchFilter) params.set('branch', branchFilter)
    return params.toString()
  }, [page, search, targetRoleFilter, branchFilter])

  const { data: presetsData = { items: [], total: 0 }, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['onboarding-presets', queryString],
    queryFn: () => apiFetch(`/onboarding-presets/?${queryString}`),
  })

  const { data: stockData = { items: [] } } = useQuery({
    queryKey: ['stock', 'onboarding-kits'],
    queryFn: () => apiFetch('/stock/?page=1&per_page=200'),
    enabled: canEdit,
  })

  const { data: employeeFilterOptions = { roles: [] } } = useQuery({
    queryKey: ['onboarding-kit-roles'],
    queryFn: () => apiFetch('/employees/filter-options'),
  })

  const { data: branchOptions = [] } = useQuery({
    queryKey: ['onboarding-kit-branches'],
    queryFn: () => apiFetch('/branches'),
  })

  const available = useMemo(() => (stockData?.items || []).filter((a) => a.unused > 0), [stockData])
  const roleOptions = employeeFilterOptions?.roles || []
  const presetItems = presetsData?.items || []
  const total = presetsData?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const createMut = useMutation({
    mutationFn: (body) => apiFetch('/onboarding-presets/', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['onboarding-presets'] }),
  })

  const deleteMut = useMutation({
    mutationFn: (id) => apiFetch(`/onboarding-presets/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    onSuccess: () => {
      setDeleteTarget(null)
      qc.invalidateQueries({ queryKey: ['onboarding-presets'] })
    },
  })

  return (
    <div className="p-6 sm:p-8 max-w-4xl mx-auto space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Onboarding kits</h1>
          <p className="text-sm text-slate-600 mt-1 max-w-2xl">
            Define named bundles of <strong>catalog asset IDs</strong> for new hires. HR uses these when registering an employee (no copy-paste from
            inventory). Kits can target a <strong>role</strong> and optionally a <strong>branch</strong> so the wrong bundle is not applied by mistake.
          </p>
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

      {canEdit ? (
        <CreateKitForm
          stock={available}
          roles={roleOptions}
          branches={branchOptions}
          onCreate={(body) => createMut.mutate(body)}
          busy={createMut.isPending}
          error={createMut.error?.message}
        />
      ) : (
        <p className="text-sm text-slate-600 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          Only <strong>administrators</strong>, <strong>managers</strong>, and <strong>HR</strong> can work with onboarding kits.
        </p>
      )}

      <div className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wide">Saved kits</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 w-full sm:w-auto">
            <input
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
              placeholder="Search kit name or ID"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
            <select
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
              value={targetRoleFilter}
              onChange={(e) => {
                setTargetRoleFilter(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All roles</option>
              {roleOptions.map((role) => <option key={role} value={role}>{labelForRole(role)}</option>)}
            </select>
            <select
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
              value={branchFilter}
              onChange={(e) => {
                setBranchFilter(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All branches</option>
              {branchOptions.map((branch) => <option key={branch.branch_id} value={branch.branch_name}>{branch.branch_name}</option>)}
            </select>
          </div>
        </div>
        {isLoading ? (
          <p className="text-slate-400 animate-pulse py-8">Loading…</p>
        ) : presetItems.length === 0 ? (
          <p className="text-sm text-slate-500 border border-dashed border-slate-200 rounded-2xl p-8 text-center">No kits yet.</p>
        ) : (
          <ul className="space-y-3">
            {presetItems.map((p) => (
              <li key={p.preset_id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div>
                  <p className="font-bold text-slate-900">{p.name}</p>
                  <p className="text-xs font-mono text-slate-500 mt-1">{p.preset_id}</p>
                  <div className="flex flex-wrap gap-2 mt-2 text-xs">
                    {p.target_role ? (
                      <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-800 font-semibold">Role: {labelForRole(p.target_role)}</span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700">Any role</span>
                    )}
                    {p.branch ? (
                      <span className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-900">Branch: {p.branch}</span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-md bg-slate-50 text-slate-600">Any branch</span>
                    )}
                  </div>
                  <p className="text-xs text-slate-600 mt-2">
                    Assets:{' '}
                    <span className="font-mono">{p.asset_ids?.length ? p.asset_ids.join(', ') : '—'}</span>
                  </p>
                </div>
                {canEdit ? (
                  <button
                    type="button"
                    onClick={() => setDeleteTarget({ id: p.preset_id, name: p.name })}
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-rose-700 border border-rose-200 rounded-xl px-3 py-2 hover:bg-rose-50 shrink-0"
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={total} />
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget ? `Delete kit “${deleteTarget.name}”?` : ''}
        description="This removes the onboarding kit preset. Employees already registered are not affected."
        confirmLabel="Delete kit"
        busy={deleteMut.isPending}
        onCancel={() => !deleteMut.isPending && setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMut.mutate(deleteTarget.id)}
      />
    </div>
  )
}

function CreateKitForm({ stock, roles, branches, onCreate, busy, error }) {
  const [name, setName] = useState('')
  const [targetRole, setTargetRole] = useState('')
  const [branch, setBranch] = useState('')
  const [picked, setPicked] = useState(() => new Set())

  const toggle = (id) => {
    setPicked((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  return (
    <form
      className="rounded-2xl border border-teal-200/80 bg-teal-50/30 p-5 space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        onCreate({
          name: name.trim(),
          target_role: targetRole || null,
          branch: branch.trim() || null,
          asset_ids: [...picked],
        })
        setName('')
        setTargetRole('')
        setBranch('')
        setPicked(new Set())
      }}
    >
      <h2 className="text-sm font-bold text-teal-900 flex items-center gap-2">
        <Plus className="w-4 h-4" />
        New kit
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input required className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" placeholder="Kit name (e.g. Standard laptop employee)" value={name} onChange={(e) => setName(e.target.value)} />
        <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={targetRole} onChange={(e) => setTargetRole(e.target.value)}>
          <option value="">Target role (optional)</option>
          {roles.map((role) => <option key={role} value={role}>{labelForRole(role)}</option>)}
        </select>
        <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white sm:col-span-2" value={branch} onChange={(e) => setBranch(e.target.value)}>
          <option value="">Branch filter (optional — employee must match)</option>
          {branches.map((item) => <option key={item.branch_id} value={item.branch_name}>{item.branch_name}</option>)}
        </select>
      </div>
      <div>
        <p className="text-xs font-semibold text-slate-700 mb-2">Pick catalog lines with available quantity (unused &gt; 0)</p>
        <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-white divide-y divide-slate-100 text-sm">
          {stock.length === 0 ? (
            <p className="p-4 text-slate-500 text-xs">No stock with spare units. Add inventory first.</p>
          ) : (
            stock.map((a) => (
              <label key={a.asset_id} className="flex items-center gap-3 px-3 py-2 hover:bg-slate-50 cursor-pointer">
                <input type="checkbox" checked={picked.has(a.asset_id)} onChange={() => toggle(a.asset_id)} />
                <span className="font-mono text-xs text-slate-700">{a.asset_id}</span>
                <span className="text-slate-600 truncate flex-1">{a.name}</span>
                <span className="text-xs text-teal-700 font-semibold">{a.unused} free</span>
              </label>
            ))
          )}
        </div>
      </div>
      {error ? <p className="text-xs text-rose-600">{error}</p> : null}
      <button type="submit" disabled={busy || picked.size === 0} className="rounded-xl bg-teal-700 text-white text-sm font-semibold px-4 py-2.5 disabled:opacity-50">
        {busy ? 'Saving…' : 'Save kit'}
      </button>
    </form>
  )
}
