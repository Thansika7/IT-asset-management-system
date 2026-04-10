import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import ConfirmDialog from '@/components/ConfirmDialog'
import Pagination from '@/components/Pagination'
import { useAuth } from '@/context/AuthContext'

function toIsoOrNullFromLocal(v) {
  if (!v || !String(v).trim()) return null
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

function formatDt(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export default function Organizations() {
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin'
  const isOrgAdmin = user?.role === 'org_admin'
  const canManageBranches = isOrgAdmin
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')
  const [adminName, setAdminName] = useState('')
  const [adminWorkEmail, setAdminWorkEmail] = useState('')
  const [adminPersonalEmail, setAdminPersonalEmail] = useState('')
  const [subStartLocal, setSubStartLocal] = useState('')
  const [subEndLocal, setSubEndLocal] = useState('')
  const [createdMeta, setCreatedMeta] = useState(null)

  const [orgSearch, setOrgSearch] = useState('')
  const [orgStatusFilter, setOrgStatusFilter] = useState('')
  const [orgPage, setOrgPage] = useState(1)
  const ORG_PAGE_SIZE = 10

  const [selectedOrgId, setSelectedOrgId] = useState(null)
  const [editOrg, setEditOrg] = useState(null)
  const [branchForm, setBranchForm] = useState({ branch_name: '', location: '' })
  const [editingBranch, setEditingBranch] = useState(null)
  const [removeOrgTarget, setRemoveOrgTarget] = useState(null)
  const [removeBranchTarget, setRemoveBranchTarget] = useState(null)
  const [branchSearch, setBranchSearch] = useState('')
  const [branchStatusFilter, setBranchStatusFilter] = useState('')
  const [branchPage, setBranchPage] = useState(1)
  const BRANCH_PAGE_SIZE = 10

  const orgQuery = useMemo(() => {
    const params = new URLSearchParams({
      page: String(orgPage),
      per_page: String(ORG_PAGE_SIZE),
    })
    if (orgSearch.trim()) params.set('search', orgSearch.trim())
    if (orgStatusFilter) params.set('status', orgStatusFilter)
    return params.toString()
  }, [orgPage, orgSearch, orgStatusFilter])

  const { data = { items: [], total: 0 }, isLoading, isError, error } = useQuery({
    queryKey: ['organizations', orgQuery],
    queryFn: () => apiFetch(`/organizations/?${orgQuery}`),
  })

  const adminQuery = useQuery({
    queryKey: ['organization-admin', selectedOrgId],
    queryFn: () => apiFetch(`/organizations/${selectedOrgId}/admin`),
    enabled: Boolean(selectedOrgId),
  })

  const branchesQuery = useQuery({
    queryKey: ['organization-branches', selectedOrgId, branchSearch, branchStatusFilter, branchPage],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(branchPage),
        per_page: String(BRANCH_PAGE_SIZE),
      })
      if (branchSearch.trim()) params.set('search', branchSearch.trim())
      if (branchStatusFilter) params.set('status', branchStatusFilter)
      return apiFetch(`/organizations/${selectedOrgId}/branches?${params.toString()}`)
    },
    enabled: Boolean(selectedOrgId),
  })

  const orgRows = data?.items || []
  const orgTotal = data?.total || 0
  const orgTotalPages = Math.max(1, Math.ceil(orgTotal / ORG_PAGE_SIZE))
  const orgStatusOptions = useMemo(() => {
    const setValues = new Set(orgRows.map((row) => row.subscription_status).filter(Boolean))
    return [...setValues].sort((a, b) => String(a).localeCompare(String(b)))
  }, [orgRows])

  const branchRows = branchesQuery.data?.items || []
  const branchTotal = branchesQuery.data?.total || 0
  const branchTotalPages = Math.max(1, Math.ceil(branchTotal / BRANCH_PAGE_SIZE))
  const branchStatusOptions = useMemo(() => {
    const setValues = new Set(branchRows.map((row) => row.status).filter(Boolean))
    return [...setValues].sort((a, b) => String(a).localeCompare(String(b)))
  }, [branchRows])

  const selectedOrg = useMemo(
    () => orgRows.find((o) => o.organization_id === selectedOrgId) || null,
    [orgRows, selectedOrgId],
  )

  const createMut = useMutation({
    mutationFn: (body) => apiFetch('/organizations/', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: (payload) => {
      qc.invalidateQueries({ queryKey: ['organizations'] })
      setName('')
      setDomain('')
      setAdminName('')
      setAdminWorkEmail('')
      setAdminPersonalEmail('')
      setSubStartLocal('')
      setSubEndLocal('')
      setCreatedMeta(payload)
    },
  })

  const revokeMut = useMutation({
    mutationFn: (orgId) => apiFetch(`/organizations/${orgId}/revoke`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['organizations'] }),
  })

  const restoreMut = useMutation({
    mutationFn: (orgId) => apiFetch(`/organizations/${orgId}/restore`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['organizations'] }),
  })

  const deleteOrgMut = useMutation({
    mutationFn: (orgId) => apiFetch(`/organizations/${orgId}`, { method: 'DELETE' }),
    onSuccess: (_, orgId) => {
      setRemoveOrgTarget(null)
      qc.invalidateQueries({ queryKey: ['organizations'] })
      qc.removeQueries({ queryKey: ['organization-admin', orgId] })
      qc.removeQueries({ queryKey: ['organization-branches', orgId] })
      if (selectedOrgId === orgId) {
        setSelectedOrgId(null)
        setEditingBranch(null)
      }
    },
  })

  const updateOrgMut = useMutation({
    mutationFn: ({ orgId, body }) =>
      apiFetch(`/organizations/${orgId}`, { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organizations'] })
      setEditOrg(null)
    },
  })

  const createBranchMut = useMutation({
    mutationFn: ({ orgId, body }) =>
      apiFetch(`/organizations/${orgId}/branches`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organization-branches', selectedOrgId] })
      setBranchForm({ branch_name: '', location: '' })
    },
  })

  const updateBranchMut = useMutation({
    mutationFn: ({ orgId, branchId, body }) =>
      apiFetch(`/organizations/${orgId}/branches/${branchId}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organization-branches', selectedOrgId] })
      setEditingBranch(null)
    },
  })

  const deleteBranchMut = useMutation({
    mutationFn: ({ orgId, branchId }) =>
      apiFetch(`/organizations/${orgId}/branches/${branchId}`, { method: 'DELETE' }),
    onSuccess: () => {
      setRemoveBranchTarget(null)
      qc.invalidateQueries({ queryKey: ['organization-branches', selectedOrgId] })
    },
  })

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Organizations</h1>
        <p className="text-sm text-slate-600 mt-1">
          {isSuperAdmin
            ? 'Super Admin workspace for onboarding, subscription windows, and branch structure.'
            : 'Organization workspace for branch structure management.'}
        </p>
      </div>

      {isSuperAdmin ? (
      <form
        className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3 shadow-sm"
        onSubmit={(e) => {
          e.preventDefault()
          const body = {
            organization_name: name,
            domain: domain || null,
            admin_name: adminName,
            admin_work_email: adminWorkEmail,
            admin_personal_email: adminPersonalEmail,
          }
          const subscriptionStartIso = toIsoOrNullFromLocal(subStartLocal)
          const subscriptionEndIso = toIsoOrNullFromLocal(subEndLocal)
          if (subscriptionStartIso) body.subscription_start_at = subscriptionStartIso
          if (subscriptionEndIso) body.subscription_end_at = subscriptionEndIso
          createMut.mutate(body)
        }}
      >
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wide">Register organization</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            required
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Organization name"
            value={name}
            onChange={(ev) => setName(ev.target.value)}
          />
          <input
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Domain (example.com)"
            value={domain}
            onChange={(ev) => setDomain(ev.target.value)}
          />
          <input
            required
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Org admin name"
            value={adminName}
            onChange={(ev) => setAdminName(ev.target.value)}
          />
          <input
            required
            type="email"
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Org admin work email"
            value={adminWorkEmail}
            onChange={(ev) => setAdminWorkEmail(ev.target.value)}
          />
          <input
            required
            type="email"
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm md:col-span-2"
            placeholder="Org admin personal email (credentials sent here)"
            value={adminPersonalEmail}
            onChange={(ev) => setAdminPersonalEmail(ev.target.value)}
          />
          <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-xs text-slate-600 space-y-1 block">
              <span className="font-medium text-slate-700">Subscription start (optional)</span>
              <input
                type="datetime-local"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                value={subStartLocal}
                onChange={(ev) => setSubStartLocal(ev.target.value)}
              />
            </label>
            <label className="text-xs text-slate-600 space-y-1 block">
              <span className="font-medium text-slate-700">Subscription end: (optional)</span>
              <input
                type="datetime-local"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                value={subEndLocal}
                onChange={(ev) => setSubEndLocal(ev.target.value)}
              />
            </label>
          </div>
        </div>
        <button
          type="submit"
          disabled={createMut.isPending}
          className="rounded-xl bg-slate-900 text-white text-sm font-medium px-4 py-2 disabled:opacity-50"
        >
          {createMut.isPending ? 'Creating...' : 'Create organization'}
        </button>
        {createMut.isError ? <p className="text-xs text-rose-600">{createMut.error?.message}</p> : null}
        {createdMeta ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
            <p className="font-semibold">Organization onboarded successfully.</p>
            <p>Organization ID: {createdMeta.organization_id}</p>
            <p>Org Admin ID: {createdMeta.org_admin_employee_id}</p>
            <p>Credentials sent to: {createdMeta.org_admin_personal_email}</p>
          </div>
        ) : null}
      </form>
      ) : null}

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm md:col-span-2"
            placeholder="Search organization, domain, status, admin email..."
            value={orgSearch}
            onChange={(e) => {
              setOrgSearch(e.target.value)
              setOrgPage(1)
            }}
          />
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={orgStatusFilter}
            onChange={(e) => {
              setOrgStatusFilter(e.target.value)
              setOrgPage(1)
            }}
          >
            <option value="">All subscription statuses</option>
            {orgStatusOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        {isLoading ? (
          <div className="p-6 text-sm text-slate-500">Loading organizations...</div>
        ) : isError ? (
          <div className="p-6 text-sm text-rose-600">{error?.message}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm min-w-[900px]">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Organization</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Domain</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Subscription</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Period</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Created</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {orgRows.map((org) => (
                  <tr key={org.organization_id} className={selectedOrgId === org.organization_id ? 'bg-slate-50/80' : ''}>
                    <td className="p-4 font-medium text-slate-900">{org.organization_name}</td>
                    <td className="p-4 text-slate-700">{org.domain || 'Not set'}</td>
                    <td className="p-4 text-slate-700">{org.subscription_status}</td>
                    <td className="p-4 text-slate-600 text-xs leading-relaxed">
                      <div>Start: {formatDt(org.subscription_start_at)}</div>
                      <div>End: {formatDt(org.subscription_end_at)}</div>
                    </td>
                    <td className="p-4 text-slate-600">{org.created_at ? new Date(org.created_at).toLocaleString() : '—'}</td>
                    <td className="p-4 text-right space-x-1 whitespace-nowrap">
                      <button
                        type="button"
                        className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-800 hover:bg-slate-50"
                        onClick={() => setSelectedOrgId(org.organization_id)}
                      >
                        Manage
                      </button>
                      {isSuperAdmin ? (
                        <>
                      <button
                        type="button"
                        className="rounded-lg border border-slate-200 px-2 py-1 text-xs text-slate-800 hover:bg-slate-50"
                        onClick={() => {
                          setEditOrg({
                            ...org,
                            subscription_status: org.subscription_status,
                          })
                        }}
                      >
                        Edit
                      </button>
                      {org.subscription_status === 'INACTIVE' ? (
                        <button
                          type="button"
                          disabled={restoreMut.isPending}
                          className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs text-emerald-900 disabled:opacity-50"
                          onClick={() => restoreMut.mutate(org.organization_id)}
                        >
                          Restore
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={revokeMut.isPending}
                          className="rounded-lg border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-900 disabled:opacity-50"
                          onClick={() => revokeMut.mutate(org.organization_id)}
                        >
                          Revoke
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={deleteOrgMut.isPending}
                        className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 disabled:opacity-50"
                        onClick={() =>
                          setRemoveOrgTarget({ id: org.organization_id, name: org.organization_name })
                        }
                      >
                        Remove
                      </button>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {orgRows.length === 0 ? (
                  <tr>
                    <td className="p-6 text-slate-500" colSpan={6}>
                      No organizations yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={orgPage} totalPages={orgTotalPages} onPageChange={setOrgPage} pageSize={ORG_PAGE_SIZE} total={orgTotal} />
      </div>
      {deleteOrgMut.isError ? (
        <p className="text-sm text-rose-600">{deleteOrgMut.error?.message}</p>
      ) : null}

      {selectedOrgId && selectedOrg ? (
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50/40 p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">Manage: {selectedOrg.organization_name}</h2>
              <p className="text-xs text-slate-600">{selectedOrg.organization_id}</p>
            </div>
            <button
              type="button"
              className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-800"
              onClick={() => {
                setSelectedOrgId(null)
                setEditingBranch(null)
              }}
            >
              Close panel
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">Org admin</h3>
                <button
                  type="button"
                  className="text-xs font-medium text-indigo-700 hover:underline"
                  onClick={() => adminQuery.refetch()}
                >
                  Refresh
                </button>
              </div>
              {adminQuery.isLoading ? (
                <p className="text-xs text-slate-500">Loading admin details...</p>
              ) : adminQuery.isError ? (
                <p className="text-xs text-rose-600">{adminQuery.error?.message}</p>
              ) : adminQuery.data ? (
                <dl className="text-xs space-y-2 text-slate-700">
                  <div>
                    <dt className="text-slate-500">Name</dt>
                    <dd className="font-medium">{adminQuery.data.org_admin_name}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Work email</dt>
                    <dd>{adminQuery.data.org_admin_work_email}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Personal email</dt>
                    <dd>{adminQuery.data.org_admin_personal_email}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Admin employee ID</dt>
                    <dd className="font-mono">{adminQuery.data.org_admin_employee_id}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Subscription (org)</dt>
                    <dd>
                      {adminQuery.data.subscription_status} · start {formatDt(adminQuery.data.subscription_start_at)} · end{' '}
                      {formatDt(adminQuery.data.subscription_end_at)}
                    </dd>
                  </div>
                </dl>
              ) : null}
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">Branches</h3>
                {!canManageBranches ? (
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">View only</span>
                ) : null}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <input
                  className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                  placeholder="Search branch, location, status..."
                  value={branchSearch}
                  onChange={(ev) => {
                    setBranchSearch(ev.target.value)
                    setBranchPage(1)
                  }}
                />
                <select
                  className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                  value={branchStatusFilter}
                  onChange={(ev) => {
                    setBranchStatusFilter(ev.target.value)
                    setBranchPage(1)
                  }}
                >
                  <option value="">All branch statuses</option>
                  {branchStatusOptions.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </div>
              {canManageBranches ? (
                <form
                  className="flex flex-wrap gap-2 items-end border-b border-slate-100 pb-3"
                  onSubmit={(ev) => {
                    ev.preventDefault()
                    if (!branchForm.branch_name.trim()) return
                    createBranchMut.mutate({
                      orgId: selectedOrgId,
                      body: {
                        branch_name: branchForm.branch_name.trim(),
                        location: branchForm.location.trim() || null,
                      },
                    })
                  }}
                >
                  <input
                    className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs flex-1 min-w-[120px]"
                    placeholder="Branch name"
                    value={branchForm.branch_name}
                    onChange={(ev) => setBranchForm((f) => ({ ...f, branch_name: ev.target.value }))}
                  />
                  <input
                    className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs flex-1 min-w-[120px]"
                    placeholder="Location (optional)"
                    value={branchForm.location}
                    onChange={(ev) => setBranchForm((f) => ({ ...f, location: ev.target.value }))}
                  />
                  <button
                    type="submit"
                    disabled={createBranchMut.isPending}
                    className="rounded-lg bg-slate-900 text-white text-xs px-3 py-1.5 disabled:opacity-50"
                  >
                    Add branch
                  </button>
                </form>
              ) : null}
              {createBranchMut.isError ? (
                <p className="text-xs text-rose-600">{createBranchMut.error?.message}</p>
              ) : null}

              {branchesQuery.isLoading ? (
                <p className="text-xs text-slate-500">Loading branches...</p>
              ) : branchesQuery.isError ? (
                <p className="text-xs text-rose-600">{branchesQuery.error?.message}</p>
              ) : (
                <ul className="space-y-2 max-h-64 overflow-y-auto">
                  {branchRows.map((b) =>
                    editingBranch?.branch_id === b.branch_id ? (
                      <li key={b.branch_id} className="rounded-lg border border-slate-200 p-2 space-y-2">
                        <input
                          className="w-full rounded border border-slate-200 px-2 py-1 text-xs"
                          value={editingBranch.branch_name}
                          onChange={(ev) => setEditingBranch((eb) => ({ ...eb, branch_name: ev.target.value }))}
                        />
                        <input
                          className="w-full rounded border border-slate-200 px-2 py-1 text-xs"
                          placeholder="Location"
                          value={editingBranch.location || ''}
                          onChange={(ev) => setEditingBranch((eb) => ({ ...eb, location: ev.target.value }))}
                        />
                        <select
                          className="w-full rounded border border-slate-200 px-2 py-1 text-xs"
                          value={editingBranch.status}
                          onChange={(ev) => setEditingBranch((eb) => ({ ...eb, status: ev.target.value }))}
                        >
                          <option value="ACTIVE">ACTIVE</option>
                          <option value="INACTIVE">INACTIVE</option>
                        </select>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            className="text-xs font-medium text-white bg-slate-900 rounded px-2 py-1"
                            onClick={() =>
                              updateBranchMut.mutate({
                                orgId: selectedOrgId,
                                branchId: b.branch_id,
                                body: {
                                  branch_name: editingBranch.branch_name.trim(),
                                  location: editingBranch.location?.trim() || null,
                                  status: editingBranch.status,
                                },
                              })
                            }
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            className="text-xs text-slate-600"
                            onClick={() => setEditingBranch(null)}
                          >
                            Cancel
                          </button>
                        </div>
                      </li>
                    ) : (
                      <li
                        key={b.branch_id}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-100 bg-slate-50/50 px-3 py-2"
                      >
                        <div>
                          <p className="text-sm font-medium text-slate-900">{b.branch_name}</p>
                          <p className="text-xs text-slate-600">
                            {b.branch_id} · {b.location || 'No location'} · {b.status}
                          </p>
                        </div>
                        {canManageBranches ? (
                          <div className="flex gap-1">
                            <button
                              type="button"
                              className="text-xs rounded border border-slate-200 bg-white px-2 py-1"
                              onClick={() =>
                                setEditingBranch({
                                  branch_id: b.branch_id,
                                  branch_name: b.branch_name,
                                  location: b.location || '',
                                  status: b.status,
                                })
                              }
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="text-xs rounded border border-rose-200 bg-rose-50 px-2 py-1 text-rose-800"
                              onClick={() =>
                                setRemoveBranchTarget({
                                  orgId: selectedOrgId,
                                  branchId: b.branch_id,
                                  name: b.branch_name,
                                })
                              }
                            >
                              Delete
                            </button>
                          </div>
                        ) : null}
                      </li>
                    ),
                  )}
                  {branchRows.length === 0 ? (
                    <li className="text-xs text-slate-500">No branches yet for this organization.</li>
                  ) : null}
                </ul>
              )}
              <Pagination page={branchPage} totalPages={branchTotalPages} onPageChange={setBranchPage} pageSize={BRANCH_PAGE_SIZE} total={branchTotal} />
              {deleteBranchMut.isError ? (
                <p className="text-xs text-rose-600">{deleteBranchMut.error?.message}</p>
              ) : null}
              {updateBranchMut.isError ? (
                <p className="text-xs text-rose-600">{updateBranchMut.error?.message}</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {editOrg ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center p-4 bg-black/40" role="dialog">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-5 space-y-3">
            <h3 className="text-sm font-bold text-slate-900">Edit organization subscription</h3>
            <p className="text-xs text-slate-500">{editOrg.organization_name}</p>
            <label className="block text-xs text-slate-600 space-y-1">
              <span>Status</span>
              <select
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                value={editOrg.subscription_status}
                onChange={(ev) => setEditOrg((o) => ({ ...o, subscription_status: ev.target.value }))}
              >
                <option value="ACTIVE">ACTIVE</option>
                <option value="INACTIVE">INACTIVE</option>
                <option value="SUSPENDED">SUSPENDED</option>
                <option value="TRIAL">TRIAL</option>
              </select>
            </label>
            <label className="block text-xs text-slate-600 space-y-1">
              <span>Subscription start</span>
              <input
                type="datetime-local"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                value={
                  editOrg.subscription_start_at
                    ? (() => {
                        try {
                          const d = new Date(editOrg.subscription_start_at)
                          const pad = (n) => String(n).padStart(2, '0')
                          return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
                        } catch {
                          return ''
                        }
                      })()
                    : ''
                }
                onChange={(ev) => {
                  const v = ev.target.value
                  setEditOrg((o) => ({
                    ...o,
                    subscription_start_at: v ? toIsoOrNullFromLocal(v) : null,
                  }))
                }}
              />
            </label>
            <label className="block text-xs text-slate-600 space-y-1">
              <span>Subscription end</span>
              <input
                type="datetime-local"
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                value={
                  editOrg.subscription_end_at
                    ? (() => {
                        try {
                          const d = new Date(editOrg.subscription_end_at)
                          const pad = (n) => String(n).padStart(2, '0')
                          return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
                        } catch {
                          return ''
                        }
                      })()
                    : ''
                }
                onChange={(ev) => {
                  const v = ev.target.value
                  setEditOrg((o) => ({
                    ...o,
                    subscription_end_at: v ? toIsoOrNullFromLocal(v) : null,
                  }))
                }}
              />
            </label>
            {updateOrgMut.isError ? (
              <p className="text-xs text-rose-600">{updateOrgMut.error?.message}</p>
            ) : null}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm"
                onClick={() => setEditOrg(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={updateOrgMut.isPending}
                className="rounded-xl bg-slate-900 text-white text-sm px-4 py-2 disabled:opacity-50"
                onClick={() => {
                  const body = { subscription_status: editOrg.subscription_status }
                  if (editOrg.subscription_start_at !== undefined) {
                    body.subscription_start_at = editOrg.subscription_start_at
                  }
                  if (editOrg.subscription_end_at !== undefined) {
                    body.subscription_end_at = editOrg.subscription_end_at
                  }
                  updateOrgMut.mutate({ orgId: editOrg.organization_id, body })
                }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={Boolean(removeOrgTarget)}
        title={removeOrgTarget ? `Remove “${removeOrgTarget.name}” permanently?` : ''}
        description={
          'This will delete the organization and all tenant data tied to it, including employees, branches, permissions, assets, requests, tracking records, CMDB items, categories, attribute values, and audit logs for that organization. This cannot be undone.'
        }
        confirmLabel="Remove organization"
        busy={deleteOrgMut.isPending}
        onCancel={() => !deleteOrgMut.isPending && setRemoveOrgTarget(null)}
        onConfirm={() => removeOrgTarget && deleteOrgMut.mutate(removeOrgTarget.id)}
      />
      <ConfirmDialog
        open={Boolean(removeBranchTarget)}
        title={removeBranchTarget ? `Delete branch “${removeBranchTarget.name}”?` : ''}
        description="Branches can only be deleted when no employees or assets are assigned to them."
        confirmLabel="Delete branch"
        busy={deleteBranchMut.isPending}
        onCancel={() => !deleteBranchMut.isPending && setRemoveBranchTarget(null)}
        onConfirm={() =>
          removeBranchTarget &&
          deleteBranchMut.mutate({ orgId: removeBranchTarget.orgId, branchId: removeBranchTarget.branchId })
        }
      />
    </div>
  )
}
