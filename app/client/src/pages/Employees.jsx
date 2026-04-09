import React, { useEffect, useMemo, useRef, useState } from 'react'
import Pagination from '@/components/Pagination'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import { apiFetch } from '@/lib/api'
import { R, canRegisterEmployees, canDeactivateEmployees, labelForRole, canManagePermissions } from '@/lib/roles'
import { useAuth } from '@/context/AuthContext'
import { RefreshCw, UserPlus, X, UserMinus, Shield, Pencil } from 'lucide-react'

export default function Employees() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [deact, setDeact] = useState(null)
  const [editUser, setEditUser] = useState(null)
  const [permsUser, setPermsUser] = useState(null)
  const [banner, setBanner] = useState(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('active')
  const [branchFilter, setBranchFilter] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [organizationFilter, setOrganizationFilter] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 10

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      per_page: String(PAGE_SIZE),
    })
    if (search.trim()) params.set('search', search.trim())
    if (statusFilter) params.set('status', statusFilter)
    if (branchFilter) params.set('branch_id', branchFilter)
    if (roleFilter) params.set('role', roleFilter)
    if (organizationFilter) params.set('organization_id', organizationFilter)
    return params.toString()
  }, [page, search, statusFilter, branchFilter, roleFilter, organizationFilter])

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['employees', queryString],
    queryFn: () => apiFetch(`/employees/?${queryString}`),
  })

  const { data: branchOptions = [] } = useQuery({
    queryKey: ['employee-filter-branches'],
    queryFn: () => apiFetch('/branches'),
  })

  const { data: orgOptionsRaw = { items: [] } } = useQuery({
    queryKey: ['employee-filter-organizations'],
    queryFn: () => apiFetch('/organizations?page=1&per_page=200'),
  })

  const orgOptions = orgOptionsRaw?.items || []

  const { data: employeeFilterOptions = { roles: [], statuses: [] } } = useQuery({
    queryKey: ['employee-filter-options'],
    queryFn: () => apiFetch('/employees/filter-options'),
  })

  const regMut = useMutation({
    mutationFn: async (body) => {
      const { employee_status, ...payload } = body
      const created = await apiFetch('/employees/register', { method: 'POST', body: JSON.stringify(payload) })
      if (employee_status === 'inactive' && created?.employee_id) {
        await apiFetch(`/employees/${created.employee_id}`, {
          method: 'PUT',
          body: JSON.stringify({ is_active: false }),
        })
      }
      return created
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['employees'] })
      setOpen(false)
      const pe = data?.personal_email || 'their personal email'
      setBanner({
        kind: 'success',
        text: `Employee registered.\n\nCompany login: ${data?.email ?? '—'}\nA temporary password was emailed to ${pe}. They must change it on first sign-in.`,
      })
    },
  })

  const deactivateMut = useMutation({
    mutationFn: (empId) => apiFetch(`/employees/${empId}/deactivate`, { method: 'POST' }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['employees'] })
      qc.invalidateQueries({ queryKey: ['stock'] })
      qc.invalidateQueries({ queryKey: ['tracking'] })
      qc.invalidateQueries({ queryKey: ['my-assets'] })
      setDeact(null)
      const n = res?.recovered_hardware
      setBanner({
        kind: 'success',
        text:
          typeof n === 'number'
            ? `Employee removed from the database. Recovered ${n} active assignment(s) to stock.`
            : 'Employee removed from the database.',
      })
    },
  })

  const columns = useMemo(
    () => [
      {
        header: 'Name',
        accessorKey: 'name',
        cell: (c) => <span className="font-semibold text-slate-900">{c.getValue()}</span>,
      },
      {
        header: 'Role',
        accessorKey: 'role',
        cell: (c) => {
          const r = String(c.getValue() || '').toLowerCase()
          const styles = {
            [R.ADMIN]: 'bg-violet-100 text-violet-800 border-violet-200',
            [R.HR]: 'bg-pink-100 text-pink-800 border-pink-200',
            [R.MANAGER]: 'bg-blue-100 text-blue-800 border-blue-200',
            [R.SUPPORT_TEAM]: 'bg-cyan-100 text-cyan-800 border-cyan-200',
            [R.EMPLOYEE]: 'bg-slate-100 text-slate-700 border-slate-200',
          }
          return (
            <span className={`px-2.5 py-1 border rounded-lg text-[11px] font-bold uppercase tracking-wide ${styles[r] || styles[R.EMPLOYEE]}`}>
              {labelForRole(r)}
            </span>
          )
        },
      },
      { header: 'Employee ID', accessorKey: 'employee_id', cell: (c) => <span className="font-mono text-xs text-slate-600">{c.getValue()}</span> },
      { header: 'Branch', accessorKey: 'branch', cell: (c) => c.getValue() || '—' },
      { header: 'Email', accessorKey: 'email', cell: (c) => <span className="font-mono text-xs text-slate-600">{c.getValue()}</span> },
      {
        header: 'Status',
        accessorKey: 'is_active',
        cell: (c) =>
          c.getValue() ? (
            <span className="text-emerald-700 text-xs font-semibold">Active</span>
          ) : (
            <span className="text-rose-600 text-xs font-semibold">Inactive</span>
          ),
      },
      {
        id: 'actions',
        header: 'Actions',
        cell: ({ row }) => {
          const emp = row.original
          if (!emp?.is_active) return <span className="text-slate-400 text-xs">—</span>
          
          return (
            <div className="flex gap-2 items-center">
              {canManagePermissions(user.role, user.permissions) && (user.employeeId !== emp.employee_id) && (
                <button
                  type="button"
                  onClick={() => setPermsUser({ id: emp.employee_id, name: emp.name })}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1.5 text-xs font-semibold text-violet-800 hover:bg-violet-100"
                >
                  <Shield className="w-3.5 h-3.5" />
                  Permissions
                </button>
              )}
              {canRegisterEmployees(user.role) && (user.employeeId !== emp.employee_id) && (
                <button
                  type="button"
                  onClick={() => setEditUser({ id: emp.employee_id, name: emp.name })}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-xs font-semibold text-teal-800 hover:bg-teal-100"
                >
                  <Pencil className="w-3.5 h-3.5" />
                  Edit
                </button>
              )}
              {canDeactivateEmployees(user.role) && (user.employeeId !== emp.employee_id) && (
                <button
                  type="button"
                  onClick={() => setDeact({ id: emp.employee_id, name: emp.name })}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-semibold text-rose-800 hover:bg-rose-100"
                >
                  <UserMinus className="w-3.5 h-3.5" />
                  Remove
                </button>
              )}
              {(!canDeactivateEmployees(user.role) && !canManagePermissions(user.role, user.permissions)) && (
                <span className="text-slate-400 text-xs">—</span>
              )}
            </div>
          )
        },
      },
    ],
    [user.role, user.employeeId],
  )

  const rows = data?.items || []
  const totalItems = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE))
  const roleOptions = employeeFilterOptions?.roles || []
  const statusOptions = employeeFilterOptions?.statuses || []

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Team</h1>
          <p className="text-sm text-slate-600 mt-1">
            Active employees from <code className="text-xs bg-slate-100 px-1 rounded">GET /employees/</code>. HR and admin
            can <strong className="font-medium text-slate-800">remove</strong> an employee (deleted from the database) and recover hardware to stock.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {canRegisterEmployees(user.role) ? (
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 text-white px-4 py-2 text-sm font-semibold hover:bg-slate-800"
            >
              <UserPlus className="w-4 h-4" />
              Register
            </button>
          ) : null}
        </div>
      </div>

      {banner ? (
        <div
          className={`rounded-xl border px-4 py-3 text-sm flex justify-between gap-3 items-start ${
            banner.kind === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
              : 'border-slate-200 bg-slate-50 text-slate-800'
          }`}
        >
          <span className="whitespace-pre-wrap">{banner.text}</span>
          <button
            type="button"
            className="shrink-0 text-sm font-medium text-slate-600 hover:text-slate-900"
            onClick={() => setBanner(null)}
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {open && canRegisterEmployees(user.role) ? (
        <RegisterModal
          onClose={() => setOpen(false)}
          onSubmit={(body) => regMut.mutate(body)}
          busy={regMut.isPending}
          error={regMut.error?.message}
        />
      ) : null}

      {editUser ? (
        <EditEmployeeModal
          empId={editUser.id}
          name={editUser.name}
          onClose={() => setEditUser(null)}
          onSaved={(message) => setBanner({ kind: 'success', text: message })}
        />
      ) : null}

      {deact ? (
        <ConfirmDeactivate
          name={deact.name}
          empId={deact.id}
          busy={deactivateMut.isPending}
          error={deactivateMut.error?.message}
          onCancel={() => setDeact(null)}
          onConfirm={() => deactivateMut.mutate(deact.id)}
        />
      ) : null}

      {permsUser ? (
        <PermissionsModal
          empId={permsUser.id}
          name={permsUser.name}
          onClose={() => setPermsUser(null)}
          onSaved={(message) => setBanner({ kind: 'success', text: message })}
        />
      ) : null}

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 grid grid-cols-1 md:grid-cols-6 gap-3">
          <input
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm md:col-span-2"
            placeholder="Search name, email, role, branch, organization..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
          />
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All status</option>
            {statusOptions.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
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
            {branchOptions.map((b) => (
              <option key={b.branch_id} value={b.branch_id}>{b.branch_name}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={roleFilter}
            onChange={(e) => {
              setRoleFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All roles</option>
            {roleOptions.map((role) => (
              <option key={role} value={role}>{labelForRole(role)}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={organizationFilter}
            onChange={(e) => {
              setOrganizationFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All organizations</option>
            {orgOptions.map((org) => (
              <option key={org.organization_id} value={org.organization_id}>{org.organization_name}</option>
            ))}
          </select>
        </div>
        {isLoading ? (
          <div className="p-16 text-center text-slate-400 animate-pulse">Loading…</div>
        ) : isError ? (
          <div className="p-6 text-rose-700 text-sm">{error?.message}</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm min-w-[900px]">
                <thead>
                  {table.getHeaderGroups().map((hg) => (
                    <tr key={hg.id} className="bg-slate-50 border-b border-slate-200">
                      {hg.headers.map((h) => (
                        <th
                          key={h.id}
                          className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider cursor-pointer"
                          onClick={h.column.getToggleSortingHandler()}
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {table.getRowModel().rows.map((row) => (
                    <tr key={row.id} className="hover:bg-slate-50/80">
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="p-4">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={totalItems} />
          </>
        )}
      </div>

    </div>
  )
}

function ConfirmDeactivate({ name, empId, busy, error, onCancel, onConfirm }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" aria-label="Close" onClick={onCancel} />
      <div className="relative w-full max-w-md rounded-2xl bg-white border border-slate-200 shadow-xl p-6">
        <h3 className="text-lg font-bold text-slate-900">Remove employee?</h3>
        <p className="text-sm text-slate-600 mt-2">
          <strong>{name}</strong> <span className="font-mono text-xs text-slate-500">({empId})</span> will be <strong>permanently deleted</strong> from the database (including their requests and tracking history). Open assignments are returned to inventory first (
          <code className="text-xs bg-slate-100 px-1 rounded">POST /employees/…/deactivate</code>).
        </p>
        {error ? <p className="text-xs text-rose-600 mt-3">{error}</p> : null}
        <div className="flex gap-2 mt-5">
          <button type="button" onClick={onCancel} className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium">
            Cancel
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onConfirm}
            className="flex-1 rounded-xl bg-rose-600 text-white py-2.5 text-sm font-semibold disabled:opacity-50"
          >
            {busy ? 'Working…' : 'Remove'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RegisterModal({ onClose, onSubmit, busy, error }) {
  const { user } = useAuth()
  const { data: filterOptions = { roles: [], statuses: [] } } = useQuery({
    queryKey: ['employee-filter-options-register'],
    queryFn: () => apiFetch('/employees/filter-options'),
  })
  const { data: orgOptionsRaw = { items: [] } } = useQuery({
    queryKey: ['employee-filter-organizations-register'],
    queryFn: () => apiFetch('/organizations?page=1&per_page=200'),
  })
  const { data: presets = [] } = useQuery({
    queryKey: ['onboarding-presets'],
    queryFn: () => apiFetch('/onboarding-presets/'),
  })

  const { data: branches = [] } = useQuery({
    queryKey: ['employee-register-branches'],
    queryFn: () => apiFetch('/branches'),
  })

  const { data: stockRaw = { items: [] } } = useQuery({
    queryKey: ['stock-register-modal'],
    queryFn: () => apiFetch('/stock/?page=1&per_page=200'),
  })

  const [name, setName] = useState('')
  const [personalEmail, setPersonalEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [organizationId, setOrganizationId] = useState(user?.organizationId || '')
  const [branchId, setBranchId] = useState('')
  const [role, setRole] = useState(filterOptions.roles?.[0] || R.EMPLOYEE)
  const [employeeStatus, setEmployeeStatus] = useState('active')
  const [presetId, setPresetId] = useState('')
  const [picked, setPicked] = useState(() => new Set())
  const [extraIds, setExtraIds] = useState('')
  const formRef = useRef(null)

  const orgOptions = orgOptionsRaw?.items || []
  const roleOptions = filterOptions.roles || []
  const statusOptions = filterOptions.statuses || []
  const stock = stockRaw?.items || []

  const availableStock = useMemo(() => stock.filter((a) => a.unused > 0), [stock])

  const filteredBranches = useMemo(() => {
    if (!organizationId) return branches
    return branches.filter((b) => b.organization_id === organizationId)
  }, [branches, organizationId])

  useEffect(() => {
    if (!roleOptions.length) return
    if (!roleOptions.includes(role)) {
      setRole(roleOptions[0])
    }
  }, [roleOptions, role])

  const selectedBranchName = useMemo(() => {
    const selected = branches.find((b) => b.branch_id === branchId)
    return selected?.branch_name || ''
  }, [branches, branchId])

  const compatiblePresets = useMemo(() => {
    const eb = selectedBranchName.trim()
    return presets.filter((p) => {
      if (p.target_role && p.target_role !== role) return false
      if (p.branch) {
        if (!eb || p.branch !== eb) return false
      }
      return true
    })
  }, [presets, role, selectedBranchName])

  useEffect(() => {
    if (!presetId) return
    const ok = compatiblePresets.some((p) => p.preset_id === presetId)
    if (!ok) setPresetId('')
  }, [compatiblePresets, presetId])

  const togglePick = (id) => {
    setPicked((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const extraAssetIds = useMemo(() => {
    const parts = extraIds
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    return [...new Set(parts)]
  }, [extraIds])

  const mergeOnboardingIds = () => {
    const fromPick = [...picked]
    return [...new Set([...fromPick, ...extraAssetIds])]
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" aria-label="Close" onClick={onClose} />
      <div className="relative w-full max-w-2xl rounded-2xl bg-white border border-slate-200 shadow-xl p-6 max-h-[92vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-900">Register employee</h3>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-600">
            <X className="w-5 h-5" />
          </button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          A <strong>company email</strong> and <strong>temporary password</strong> are generated automatically. Credentials are sent to the employee&apos;s{' '}
          <strong>personal email</strong> (SMTP must be configured on the server). Phone: 10 digits if provided. Choose an <strong>onboarding kit</strong> (under{' '}
          <strong>Onboarding kits</strong>) and/or tick lines with free stock — optional field for extra asset IDs.
        </p>
        <form
          ref={formRef}
          className="space-y-3"
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault()
          }}
        >
          <input
            required
            name="reg_employee_name"
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Full name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="off"
          />
          <input
            required
            name="reg_personal_email"
            type="email"
            inputMode="email"
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Personal email (receives login credentials)"
            value={personalEmail}
            onChange={(e) => setPersonalEmail(e.target.value)}
            autoComplete="off"
          />
          <input
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Phone (10 digits)"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            autoComplete="off"
          />
          <select
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={branchId}
            onChange={(e) => setBranchId(e.target.value)}
          >
            <option value="">Select branch</option>
            {filteredBranches.map((b) => (
              <option key={b.branch_id} value={b.branch_id}>
                {b.branch_name}
              </option>
            ))}
          </select>
          <select
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={organizationId}
            onChange={(e) => {
              setOrganizationId(e.target.value)
              setBranchId('')
            }}
            disabled={user?.role !== R.SUPER_ADMIN}
          >
            <option value="">Select organization</option>
            {orgOptions.map((org) => (
              <option key={org.organization_id} value={org.organization_id}>{org.organization_name}</option>
            ))}
          </select>
          <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={role} onChange={(e) => setRole(e.target.value)}>
            {roleOptions.map((item) => (
              <option key={item} value={item}>{labelForRole(item)}</option>
            ))}
          </select>
          <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={employeeStatus} onChange={(e) => setEmployeeStatus(e.target.value)}>
            {statusOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>

          <div>
            <label className="text-xs font-semibold text-slate-600">Onboarding kit (optional)</label>
            <select className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={presetId} onChange={(e) => setPresetId(e.target.value)}>
              <option value="">— None —</option>
              {compatiblePresets.map((p) => (
                <option key={p.preset_id} value={p.preset_id}>
                  {p.name} ({p.preset_id})
                  {p.target_role ? ` · ${labelForRole(p.target_role)}` : ''}
                  {p.branch ? ` · ${p.branch}` : ''}
                </option>
              ))}
            </select>
            {compatiblePresets.length === 0 && presets.length > 0 ? (
              <p className="text-[11px] text-amber-700 mt-1">No kit matches this role/branch — adjust branch or role, or create a kit.</p>
            ) : null}
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-600">Also assign from inventory (unused &gt; 0)</label>
            <div className="mt-1 max-h-36 overflow-y-auto rounded-xl border border-slate-200 divide-y divide-slate-100 text-sm">
              {availableStock.length === 0 ? (
                <p className="p-3 text-xs text-slate-500">No spare units in catalog.</p>
              ) : (
                availableStock.map((a) => (
                  <label key={a.asset_id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-50 cursor-pointer">
                    <input type="checkbox" checked={picked.has(a.asset_id)} onChange={() => togglePick(a.asset_id)} />
                    <span className="font-mono text-[11px]">{a.asset_id}</span>
                    <span className="text-slate-600 truncate text-xs">{a.name}</span>
                    <span className="text-xs text-teal-700 ml-auto">{a.unused} free</span>
                  </label>
                ))
              )}
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-600">Extra asset IDs (optional)</label>
            <input
              className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-mono text-xs"
              placeholder="Comma-separated, only if not listed above"
              value={extraIds}
              onChange={(e) => setExtraIds(e.target.value)}
              autoComplete="off"
            />
          </div>

          {error ? (
            <p className="text-xs text-rose-600 whitespace-pre-wrap break-words rounded-lg border border-rose-100 bg-rose-50 px-3 py-2">{error}</p>
          ) : null}
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium">
              Cancel
            </button>
            <button
              type="button"
              disabled={busy}
              className="flex-1 rounded-xl bg-slate-900 text-white py-2.5 text-sm font-semibold disabled:opacity-50"
              onClick={() => {
                const form = formRef.current
                if (!form?.checkValidity()) {
                  form?.reportValidity()
                  return
                }
                const nm = name.trim()
                const pe = personalEmail.trim()
                if (!nm || !pe) return
                onSubmit({
                  name: nm,
                  personal_email: pe,
                  phone: phone.trim() || null,
                  role,
                  employee_status: employeeStatus,
                  organization_id: organizationId || null,
                  branch_id: branchId || null,
                  preset_id: presetId || null,
                  onboarding_asset_ids: mergeOnboardingIds(),
                })
              }}
            >
              {busy ? 'Saving…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function EditEmployeeModal({ empId, name, onClose, onSaved }) {
  const { user } = useAuth()
  const qc = useQueryClient()

  const { data: employee, isLoading } = useQuery({
    queryKey: ['employee-detail', empId],
    queryFn: () => apiFetch(`/employees/${empId}`),
    enabled: Boolean(empId),
  })

  const { data: filterOptions = { roles: [], statuses: [] } } = useQuery({
    queryKey: ['employee-filter-options-edit'],
    queryFn: () => apiFetch('/employees/filter-options'),
  })

  const { data: orgOptionsRaw = { items: [] } } = useQuery({
    queryKey: ['employee-filter-organizations-edit'],
    queryFn: () => apiFetch('/organizations?page=1&per_page=200'),
  })

  const { data: branches = [] } = useQuery({
    queryKey: ['employee-edit-branches'],
    queryFn: () => apiFetch('/branches'),
  })

  const updateMut = useMutation({
    mutationFn: (body) => apiFetch(`/employees/${empId}`, { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employees'] })
      qc.invalidateQueries({ queryKey: ['employee-detail', empId] })
      onClose()
      onSaved?.(`Employee ${name} updated successfully.`)
    },
  })

  const [fullName, setFullName] = useState('')
  const [personalEmail, setPersonalEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [organizationId, setOrganizationId] = useState('')
  const [branchId, setBranchId] = useState('')
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('active')

  const orgOptions = orgOptionsRaw?.items || []
  const roleOptions = filterOptions.roles || []
  const statusOptions = filterOptions.statuses || []

  useEffect(() => {
    if (!employee) return
    setFullName(employee.name || '')
    setPersonalEmail(employee.personal_email || '')
    setPhone(employee.phone || '')
    setOrganizationId(employee.organization_id || user?.organizationId || '')
    setBranchId(employee.branch_id || '')
    setRole(employee.role || '')
    setStatus(employee.is_active ? 'active' : 'inactive')
  }, [employee, user?.organizationId])

  const filteredBranches = useMemo(() => {
    if (!organizationId) return branches
    return branches.filter((b) => b.organization_id === organizationId)
  }, [branches, organizationId])

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" aria-label="Close" onClick={onClose} />
      <div className="relative w-full max-w-2xl rounded-2xl bg-white border border-slate-200 shadow-xl p-6 max-h-[92vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-900">Edit employee</h3>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-600">
            <X className="w-5 h-5" />
          </button>
        </div>
        {isLoading ? (
          <div className="text-sm text-slate-400 animate-pulse">Loading employee details...</div>
        ) : (
          <div className="space-y-3">
            <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Full name" />
            <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={personalEmail} onChange={(e) => setPersonalEmail(e.target.value)} placeholder="Personal email" />
            <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone (10 digits)" />
            <select
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
              value={organizationId}
              onChange={(e) => {
                setOrganizationId(e.target.value)
                setBranchId('')
              }}
              disabled={user?.role !== R.SUPER_ADMIN}
            >
              <option value="">Select organization</option>
              {orgOptions.map((org) => (
                <option key={org.organization_id} value={org.organization_id}>{org.organization_name}</option>
              ))}
            </select>
            <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={branchId} onChange={(e) => setBranchId(e.target.value)}>
              <option value="">Select branch</option>
              {filteredBranches.map((b) => (
                <option key={b.branch_id} value={b.branch_id}>{b.branch_name}</option>
              ))}
            </select>
            <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={role} onChange={(e) => setRole(e.target.value)}>
              {roleOptions.map((item) => (
                <option key={item} value={item}>{labelForRole(item)}</option>
              ))}
            </select>
            <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
              {statusOptions.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            {updateMut.error ? <p className="text-xs text-rose-600">{updateMut.error?.message}</p> : null}
            <div className="flex gap-2 pt-2">
              <button type="button" onClick={onClose} className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium">Cancel</button>
              <button
                type="button"
                disabled={updateMut.isPending}
                className="flex-1 rounded-xl bg-teal-700 text-white py-2.5 text-sm font-semibold disabled:opacity-50"
                onClick={() => updateMut.mutate({
                  name: fullName.trim() || undefined,
                  personal_email: personalEmail.trim() || null,
                  phone: phone.trim() || null,
                  organization_id: organizationId || null,
                  branch_id: branchId || null,
                  role,
                  is_active: status === 'active',
                })}
              >
                {updateMut.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function PermissionsModal({ empId, name, onClose, onSaved }) {
  const qc = useQueryClient()
  const { data: permissions, isLoading } = useQuery({
    queryKey: ['employee-permissions', empId],
    queryFn: () => apiFetch(`/employees/${empId}/permissions`),
  })
  const { data: permissionCatalog = { modules: [] }, isLoading: isCatalogLoading } = useQuery({
    queryKey: ['employee-permissions-catalog'],
    queryFn: () => apiFetch('/employees/permissions/catalog'),
  })

  const updateMut = useMutation({
    mutationFn: (body) => apiFetch(`/employees/${empId}/permissions`, { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employee-permissions', empId] })
      onClose()
      onSaved?.(`Permissions for ${name} updated successfully.`)
    },
  })

  const [permsJson, setPermsJson] = useState({})

  useEffect(() => {
    if (permissions) {
      setPermsJson(permissions.permissions_json || {})
    }
  }, [permissions])

  const modules = useMemo(() => permissionCatalog?.modules || [], [permissionCatalog])

  const toggle = (moduleKey, actionKey) => {
    setPermsJson((prev) => {
      const modulePerms = prev?.[moduleKey] && typeof prev[moduleKey] === 'object' ? prev[moduleKey] : {}
      return {
        ...prev,
        [moduleKey]: {
          ...modulePerms,
          [actionKey]: !modulePerms[actionKey],
        },
      }
    })
  }

  const buildPermissionPayload = () => ({ permissions_json: permsJson })

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <button type="button" className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" aria-label="Close" onClick={onClose} />
      <div className="relative w-full max-w-2xl rounded-2xl bg-white border border-slate-200 shadow-xl p-6 max-h-[92vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-900">Permissions for {name}</h3>
          <button type="button" onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 text-slate-600">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        {isLoading || isCatalogLoading ? (
          <div className="flex-1 min-h-[300px] flex items-center justify-center text-slate-400 animate-pulse">Loading permissions...</div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto mb-6 pr-2 space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {modules.map((module) => (
                  <div key={module.key} className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                    <h4 className="text-sm font-bold text-slate-700 mb-3">{module.label}</h4>
                    <div className="space-y-2">
                      {module.actions.map((action) => (
                        <label key={`${module.key}-${action.key}`} className="flex items-center gap-2 cursor-pointer hover:bg-white p-1 -mx-1 rounded">
                          <input 
                            type="checkbox" 
                            className="w-4 h-4 text-violet-600 rounded border-slate-300 focus:ring-violet-600 focus:ring-2"
                            checked={Boolean(permsJson?.[module.key]?.[action.key])}
                            onChange={() => toggle(module.key, action.key)}
                          />
                          <span className="text-sm text-slate-600 select-none">{action.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
                {modules.length === 0 ? (
                  <div className="sm:col-span-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                    No permission modules are configured in the backend catalog.
                  </div>
                ) : null}
              </div>
            </div>
            
            <div className="pt-4 border-t border-slate-100 flex gap-2 shrink-0">
              {updateMut.error ? (
                <p className="w-full text-xs text-rose-600 whitespace-pre-wrap rounded-lg border border-rose-100 bg-rose-50 px-3 py-2">
                  {updateMut.error.message}
                </p>
              ) : null}
              <button 
                type="button" 
                onClick={onClose} 
                className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={updateMut.isPending}
                className="flex-1 rounded-xl bg-violet-600 hover:bg-violet-700 text-white py-2.5 text-sm font-semibold transition-colors disabled:opacity-50"
                onClick={() => updateMut.mutate(buildPermissionPayload())}
              >
                {updateMut.isPending ? 'Saving...' : 'Save Permissions'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
