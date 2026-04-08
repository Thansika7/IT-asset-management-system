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
import { RefreshCw, UserPlus, X, UserMinus, Shield } from 'lucide-react'

export default function Employees() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [deact, setDeact] = useState(null)
  const [permsUser, setPermsUser] = useState(null)

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['employees'],
    queryFn: () => apiFetch('/employees/'),
  })

  const regMut = useMutation({
    mutationFn: (body) => apiFetch('/employees/register', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['employees'] })
      setOpen(false)
      const pe = data?.personal_email || 'their personal email'
      window.alert(
        `Employee registered.\n\nCompany login: ${data?.email ?? '—'}\nA temporary password was emailed to ${pe}. They must change it on first sign-in.`,
      )
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
      if (typeof n === 'number') {
        window.alert(`Employee removed from the database. Recovered ${n} active assignment(s) to stock.`)
      }
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
              {canManagePermissions(user.role) && (
                <button
                  type="button"
                  onClick={() => setPermsUser({ id: emp.employee_id, name: emp.name })}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1.5 text-xs font-semibold text-violet-800 hover:bg-violet-100"
                >
                  <Shield className="w-3.5 h-3.5" />
                  Permissions
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
              {(!canDeactivateEmployees(user.role) && !canManagePermissions(user.role)) && (
                <span className="text-slate-400 text-xs">—</span>
              )}
            </div>
          )
        },
      },
    ],
    [user.role, user.employeeId],
  )

  const [page, setPage] = useState(1)
  const PAGE_SIZE = 10
  const rows = data || []
  const totalPages = Math.ceil(rows.length / PAGE_SIZE)
  const pagedRows = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return rows.slice(start, start + PAGE_SIZE)
  }, [rows, page, PAGE_SIZE])

  const table = useReactTable({
    data: pagedRows,
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

      {open && canRegisterEmployees(user.role) ? (
        <RegisterModal
          onClose={() => setOpen(false)}
          onSubmit={(body) => regMut.mutate(body)}
          busy={regMut.isPending}
          error={regMut.error?.message}
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
        />
      ) : null}

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
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
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={rows.length} />
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
  const { data: presets = [] } = useQuery({
    queryKey: ['onboarding-presets'],
    queryFn: () => apiFetch('/onboarding-presets/'),
  })

  const { data: stock = [] } = useQuery({
    queryKey: ['stock'],
    queryFn: () => apiFetch('/stock/'),
  })

  const [name, setName] = useState('')
  const [personalEmail, setPersonalEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [branch, setBranch] = useState('')
  const [role, setRole] = useState(R.EMPLOYEE)
  const [presetId, setPresetId] = useState('')
  const [picked, setPicked] = useState(() => new Set())
  const [extraIds, setExtraIds] = useState('')
  const formRef = useRef(null)

  const availableStock = useMemo(() => stock.filter((a) => a.unused > 0), [stock])

  const compatiblePresets = useMemo(() => {
    const eb = branch.trim()
    return presets.filter((p) => {
      if (p.target_role && p.target_role !== role) return false
      if (p.branch) {
        if (!eb || p.branch !== eb) return false
      }
      return true
    })
  }, [presets, role, branch])

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
          <input
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Branch (required if kit is branch-specific)"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            autoComplete="off"
          />
          <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value={R.EMPLOYEE}>Employee</option>
            <option value={R.HR}>HR</option>
            <option value={R.MANAGER}>Manager</option>
            <option value={R.SUPPORT_TEAM}>Support</option>
            <option value={R.ADMIN}>Admin</option>
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
                  branch: branch.trim() || null,
                  role,
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

function PermissionsModal({ empId, name, onClose }) {
  const { data: permissions, isLoading } = useQuery({
    queryKey: ['employee-permissions', empId],
    queryFn: () => apiFetch(`/employees/${empId}/permissions`),
  })

  const updateMut = useMutation({
    mutationFn: (body) => apiFetch(`/employees/${empId}/permissions`, { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: () => {
      onClose()
      window.alert(`Permissions for ${name} updated successfully.`)
    },
  })

  const [perms, setPerms] = useState({})

  useEffect(() => {
    if (permissions) {
      setPerms(permissions)
    }
  }, [permissions])

  const toggle = (field) => {
    setPerms(p => ({ ...p, [field]: !p[field] }))
  }

  const groups = [
    {
      title: 'Asset Module',
      fields: [
        { key: 'can_view_assets', label: 'View Assets' },
        { key: 'can_create_assets', label: 'Create Assets' },
        { key: 'can_update_assets', label: 'Update Assets' },
        { key: 'can_delete_assets', label: 'Delete Assets' },
      ]
    },
    {
      title: 'Request Module',
      fields: [
        { key: 'can_create_request', label: 'Create Request' },
        { key: 'can_approve_request', label: 'Approve Request' },
        { key: 'can_reject_request', label: 'Reject Request' },
      ]
    },
    {
      title: 'Finance Module',
      fields: [
        { key: 'can_view_finance', label: 'View Finance' },
        { key: 'can_manage_finance', label: 'Manage Finance' },
      ]
    },
    {
      title: 'Tracking Module',
      fields: [
        { key: 'can_view_tracking', label: 'View Tracking' },
        { key: 'can_allocate_asset', label: 'Allocate Asset' },
        { key: 'can_transfer_asset', label: 'Transfer Asset' },
      ]
    },
    {
      title: 'Branch Module',
      fields: [
        { key: 'can_view_branch', label: 'View Branch' },
        { key: 'can_create_branch', label: 'Create Branch' },
        { key: 'can_update_branch', label: 'Update Branch' },
      ]
    },
    {
      title: 'Reports Module',
      fields: [
        { key: 'can_view_reports', label: 'View Reports' },
      ]
    },
    {
      title: 'Admin Module',
      fields: [
        { key: 'can_manage_users', label: 'Manage Users' },
        { key: 'can_manage_permissions', label: 'Manage Permissions' },
      ]
    }
  ]

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
        
        {isLoading ? (
          <div className="flex-1 min-h-[300px] flex items-center justify-center text-slate-400 animate-pulse">Loading permissions...</div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto mb-6 pr-2 space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {groups.map((g) => (
                  <div key={g.title} className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                    <h4 className="text-sm font-bold text-slate-700 mb-3">{g.title}</h4>
                    <div className="space-y-2">
                      {g.fields.map(f => (
                        <label key={f.key} className="flex items-center gap-2 cursor-pointer hover:bg-white p-1 -mx-1 rounded">
                          <input 
                            type="checkbox" 
                            className="w-4 h-4 text-violet-600 rounded border-slate-300 focus:ring-violet-600 focus:ring-2"
                            checked={perms[f.key] === true}
                            onChange={() => toggle(f.key)}
                          />
                          <span className="text-sm text-slate-600 select-none">{f.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="pt-4 border-t border-slate-100 flex gap-2 shrink-0">
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
                onClick={() => updateMut.mutate(perms)}
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
