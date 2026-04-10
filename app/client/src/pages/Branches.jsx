import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Pagination from '@/components/Pagination'
import ConfirmDialog from '@/components/ConfirmDialog'
import { apiFetch } from '@/lib/api'
import { useAuth } from '@/context/AuthContext'

export default function Branches() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const orgId = user?.organizationId

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [form, setForm] = useState({ branch_name: '', location: '' })
  const [editing, setEditing] = useState(null)
  const [removeTarget, setRemoveTarget] = useState(null)

  const PAGE_SIZE = 10

  const query = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      per_page: String(PAGE_SIZE),
    })
    if (search.trim()) params.set('search', search.trim())
    if (status) params.set('status', status)
    return params.toString()
  }, [page, search, status])

  const branchesQuery = useQuery({
    queryKey: ['org-admin-branches', orgId, query],
    queryFn: () => apiFetch(`/organizations/${orgId}/branches?${query}`),
    enabled: Boolean(orgId),
  })

  const createMut = useMutation({
    mutationFn: (body) => apiFetch(`/organizations/${orgId}/branches`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org-admin-branches', orgId] })
      setForm({ branch_name: '', location: '' })
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ branchId, body }) =>
      apiFetch(`/organizations/${orgId}/branches/${branchId}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org-admin-branches', orgId] })
      setEditing(null)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (branchId) => apiFetch(`/organizations/${orgId}/branches/${branchId}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org-admin-branches', orgId] })
      setRemoveTarget(null)
    },
  })

  const rows = branchesQuery.data?.items || []
  const total = branchesQuery.data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const statusOptions = useMemo(() => {
    const setValues = new Set(rows.map((r) => r.status).filter(Boolean))
    return [...setValues].sort((a, b) => String(a).localeCompare(String(b)))
  }, [rows])

  if (!orgId) {
    return (
      <div className="p-6 sm:p-8 max-w-5xl mx-auto">
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          Organization context missing for this account. Branch management is available only for organization admins.
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 sm:p-8 max-w-6xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Branches</h1>
        <p className="text-sm text-slate-600 mt-1">Manage branches for your organization only.</p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <form
          className="flex flex-wrap gap-2 items-end"
          onSubmit={(e) => {
            e.preventDefault()
            if (!form.branch_name.trim()) return
            createMut.mutate({
              branch_name: form.branch_name.trim(),
              location: form.location.trim() || null,
            })
          }}
        >
          <input
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm flex-1 min-w-[180px]"
            placeholder="Branch name"
            value={form.branch_name}
            onChange={(e) => setForm((f) => ({ ...f, branch_name: e.target.value }))}
          />
          <input
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm flex-1 min-w-[180px]"
            placeholder="Location (optional)"
            value={form.location}
            onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
          />
          <button
            type="submit"
            disabled={createMut.isPending}
            className="rounded-lg bg-slate-900 text-white text-sm px-4 py-2 disabled:opacity-50"
          >
            Add branch
          </button>
        </form>
        {createMut.isError ? <p className="text-xs text-rose-600 mt-2">{createMut.error?.message}</p> : null}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm md:col-span-2"
            placeholder="Search branch name or location..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
          />
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All statuses</option>
            {statusOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>

        {branchesQuery.isLoading ? (
          <div className="p-6 text-sm text-slate-500">Loading branches...</div>
        ) : branchesQuery.isError ? (
          <div className="p-6 text-sm text-rose-600">{branchesQuery.error?.message}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm min-w-[760px]">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200">
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Branch</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Location</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Status</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600">Created</th>
                  <th className="p-4 text-xs font-semibold uppercase tracking-wider text-slate-600 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((row) => (
                  editing?.branch_id === row.branch_id ? (
                    <tr key={row.branch_id}>
                      <td className="p-4">
                        <input
                          className="w-full rounded border border-slate-200 px-2 py-1 text-sm"
                          value={editing.branch_name}
                          onChange={(e) => setEditing((s) => ({ ...s, branch_name: e.target.value }))}
                        />
                      </td>
                      <td className="p-4">
                        <input
                          className="w-full rounded border border-slate-200 px-2 py-1 text-sm"
                          value={editing.location || ''}
                          onChange={(e) => setEditing((s) => ({ ...s, location: e.target.value }))}
                        />
                      </td>
                      <td className="p-4">
                        <select
                          className="w-full rounded border border-slate-200 px-2 py-1 text-sm"
                          value={editing.status}
                          onChange={(e) => setEditing((s) => ({ ...s, status: e.target.value }))}
                        >
                          <option value="ACTIVE">ACTIVE</option>
                          <option value="INACTIVE">INACTIVE</option>
                        </select>
                      </td>
                      <td className="p-4 text-slate-500">—</td>
                      <td className="p-4 text-right space-x-2">
                        <button
                          type="button"
                          className="rounded border border-slate-200 bg-white px-2 py-1 text-xs"
                          onClick={() => setEditing(null)}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="rounded bg-slate-900 text-white px-2 py-1 text-xs"
                          onClick={() =>
                            updateMut.mutate({
                              branchId: row.branch_id,
                              body: {
                                branch_name: editing.branch_name.trim(),
                                location: editing.location?.trim() || null,
                                status: editing.status,
                              },
                            })
                          }
                        >
                          Save
                        </button>
                      </td>
                    </tr>
                  ) : (
                    <tr key={row.branch_id}>
                      <td className="p-4 font-medium text-slate-900">{row.branch_name}</td>
                      <td className="p-4 text-slate-700">{row.location || '—'}</td>
                      <td className="p-4 text-slate-700">{row.status}</td>
                      <td className="p-4 text-slate-600">{row.created_at ? new Date(row.created_at).toLocaleString() : '—'}</td>
                      <td className="p-4 text-right space-x-2">
                        <button
                          type="button"
                          className="rounded border border-slate-200 bg-white px-2 py-1 text-xs"
                          onClick={() =>
                            setEditing({
                              branch_id: row.branch_id,
                              branch_name: row.branch_name,
                              location: row.location || '',
                              status: row.status,
                            })
                          }
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="rounded border border-rose-200 bg-rose-50 px-2 py-1 text-xs text-rose-800"
                          onClick={() => setRemoveTarget({ id: row.branch_id, name: row.branch_name })}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  )
                ))}
                {rows.length === 0 ? (
                  <tr>
                    <td className="p-6 text-slate-500" colSpan={5}>No branches found.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={total} />
      </div>

      {updateMut.isError ? <p className="text-sm text-rose-600">{updateMut.error?.message}</p> : null}
      {deleteMut.isError ? <p className="text-sm text-rose-600">{deleteMut.error?.message}</p> : null}

      <ConfirmDialog
        open={Boolean(removeTarget)}
        title={removeTarget ? `Delete branch “${removeTarget.name}”?` : ''}
        description="Branches can only be deleted when no employees or assets are assigned to them."
        confirmLabel="Delete branch"
        busy={deleteMut.isPending}
        onCancel={() => !deleteMut.isPending && setRemoveTarget(null)}
        onConfirm={() => removeTarget && deleteMut.mutate(removeTarget.id)}
      />
    </div>
  )
}
