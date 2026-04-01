import React, { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import {
  canTriage,
  canHrReview,
  canManagerReview,
  canAdminReview,
  canExecuteRequest,
  canResolveService,
  canTransferCrossBranch,
} from '@/lib/roles'
import { Eye, Plus, RefreshCw } from 'lucide-react'

const COMMON_CATEGORIES = ['Laptop', 'Monitor', 'Keyboard', 'Mouse', 'Printer', 'Phone', 'Accessory']
const REQUEST_TYPES = [
  { value: 'NEW', label: 'New allocation' },
  { value: 'REPLACE', label: 'Replace asset' },
  { value: 'SERVICE', label: 'Service / repair' },
]

function Badge({ children, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
    amber: 'bg-amber-50 text-amber-800 border-amber-200',
    emerald: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rose: 'bg-rose-50 text-rose-800 border-rose-200',
    violet: 'bg-violet-50 text-violet-800 border-violet-200',
    cyan: 'bg-cyan-50 text-cyan-800 border-cyan-200',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-lg text-[11px] font-semibold uppercase tracking-wide border ${tones[tone]}`}>
      {children}
    </span>
  )
}

function stageTone(stage) {
  if (!stage) return 'slate'
  if (stage === 'COMPLETED') return 'emerald'
  if (stage === 'REJECTED') return 'rose'
  if (String(stage).includes('APPROVAL') || stage === 'HR_VERIFICATION') return 'amber'
  if (stage === 'READY' || stage === 'IN_REPAIR') return 'violet'
  return 'cyan'
}

function formatDate(value) {
  if (!value) return 'Not available'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

function prettyBool(value) {
  if (value === true) return 'Yes'
  if (value === false) return 'No'
  return 'Pending'
}

function NewRequestForm({ onCreate, busy }) {
  const [asset_name, setAssetName] = useState('')
  const [asset_category, setCategory] = useState('Laptop')
  const [reason, setReason] = useState('')
  const [action_type, setActionType] = useState('NEW')

  const submit = (e) => {
    e.preventDefault()
    const cleanedCategory = asset_category.trim()
    const cleanedReason = reason.trim()
    const cleanedAssetName = asset_name.trim() || `${cleanedCategory} request`
    onCreate({
      asset_name: cleanedAssetName,
      asset_category: cleanedCategory,
      reason: cleanedReason,
      action_type,
    })
    setAssetName('')
    setReason('')
  }

  return (
    <form onSubmit={submit} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Create Request</h2>
          <p className="text-sm text-slate-600 mt-1">You can request by category even if you do not know the exact asset model.</p>
        </div>
        <Badge tone="cyan">For Employees</Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Asset category</label>
          <input
            required
            list="request-categories"
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
            placeholder="Laptop, Monitor, Keyboard..."
            value={asset_category}
            onChange={(e) => setCategory(e.target.value)}
          />
          <datalist id="request-categories">
            {COMMON_CATEGORIES.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
          <div className="flex flex-wrap gap-2 pt-1">
            {COMMON_CATEGORIES.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setCategory(item)}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${asset_category === item ? 'border-cyan-300 bg-cyan-50 text-cyan-700' : 'border-slate-200 bg-slate-50 text-slate-600'}`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Preferred asset name</label>
          <input
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
            placeholder="Optional: Dell Latitude, 24-inch monitor, wireless mouse..."
            value={asset_name}
            onChange={(e) => setAssetName(e.target.value)}
          />
          <p className="text-xs text-slate-500">If you leave this blank, we will send the request using the category name.</p>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Reason / context</label>
        <textarea
          required
          className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm min-h-[110px]"
          placeholder="Explain what you need, for whom, and whether this is urgent."
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Request type</label>
          <select className="rounded-2xl border border-slate-200 px-4 py-3 text-sm" value={action_type} onChange={(e) => setActionType(e.target.value)}>
            {REQUEST_TYPES.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={busy}
          className="sm:ml-auto inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 text-white text-sm font-semibold px-5 py-3 disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          Submit Request
        </button>
      </div>
    </form>
  )
}

function RequestList({ rows, selectedId, onSelect }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      <div className="border-b border-slate-200 bg-slate-50 px-5 py-4">
        <div className="flex items-center gap-3">
          <Eye className="w-4 h-4 text-slate-500" />
          <div>
            <h2 className="text-lg font-bold text-slate-900">View Requests</h2>
            <p className="text-sm text-slate-600">Select any request to see the full details and available actions.</p>
          </div>
        </div>
      </div>

      <div className="hidden md:grid grid-cols-[1.2fr_1fr_.8fr_.8fr] gap-3 px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 border-b border-slate-100">
        <span>Requester / Asset</span>
        <span>Request ID / Branch</span>
        <span>Stage</span>
        <span>Status</span>
      </div>

      <div className="divide-y divide-slate-100">
        {rows.length === 0 ? (
          <p className="text-sm text-slate-500 py-10 text-center">No requests available.</p>
        ) : rows.map((row) => (
          <button
            key={row.request_id}
            type="button"
            onClick={() => onSelect(row.request_id)}
            className={`w-full text-left px-5 py-4 transition ${selectedId === row.request_id ? 'bg-cyan-50/60' : 'bg-white hover:bg-slate-50'}`}
          >
            <div className="grid grid-cols-1 md:grid-cols-[1.2fr_1fr_.8fr_.8fr] gap-3 items-start">
              <div>
                <p className="font-semibold text-slate-900">{row.requester_name || row.emp_id}</p>
                <p className="text-xs text-slate-500 mt-1">{row.asset_name} · {row.asset_category || 'Category not set'}</p>
              </div>
              <div>
                <p className="text-sm font-mono text-slate-600">{row.request_id}</p>
                <p className="text-xs text-slate-500 mt-1">{row.requester_branch || 'Branch not set'}</p>
              </div>
              <div><Badge tone={stageTone(row.stage)}>{row.stage || 'Unknown'}</Badge></div>
              <div><Badge>{row.status || 'Unknown'}</Badge></div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function DetailPanel({ row, user, mutations }) {
  const [triageAction, setTriageAction] = useState('NEW')
  const [providedId, setProvidedId] = useState('')
  const [brokenId, setBrokenId] = useState('')
  const [resolveNotes, setResolveNotes] = useState('')
  const [repairCost, setRepairCost] = useState('0')
  const [disposable, setDisposable] = useState(false)
  const [tBranch, setTBranch] = useState('')
  const [tBrand, setTBrand] = useState('')
  const [tName, setTName] = useState('')

  useEffect(() => {
    setTriageAction('NEW')
    setProvidedId('')
    setBrokenId('')
    setResolveNotes('')
    setRepairCost('0')
    setDisposable(false)
    setTBranch('')
    setTBrand('')
    setTName('')
  }, [row?.request_id])

  if (!row) {
    return (
      <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50/80 p-8 text-center text-slate-500 text-sm">
        Select a request from the list to see complete details here.
      </div>
    )
  }

  const stage = row.stage
  const err = (m) => m.error?.message || m.error?.data?.message
  const detailRows = [
    ['Request ID', row.request_id],
    ['Asset name', row.asset_name || 'Not provided'],
    ['Category', row.asset_category || 'Not provided'],
    ['Requested by', row.requester_name || row.emp_id || 'Not available'],
    ['Requester role', row.requester_role || 'Not available'],
    ['Requester branch', row.requester_branch || 'Not available'],
    ['Employee ID', row.emp_id || 'Not available'],
    ['Stage', row.stage || 'Not available'],
    ['Status', row.status || 'Not available'],
    ['Request type', row.action_type || 'Not selected'],
    ['HR verified', prettyBool(row.hr_verified)],
    ['Requested at', formatDate(row.req_date)],
  ]

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-6">
      <div className="flex flex-col gap-3 border-b border-slate-100 pb-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={stageTone(stage)}>{stage || 'Unknown stage'}</Badge>
          <Badge>{row.status || 'Unknown status'}</Badge>
          {row.action_type ? <Badge tone="cyan">Action: {row.action_type}</Badge> : null}
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Request details</p>
          <h3 className="text-2xl font-bold text-slate-900 mt-1">{row.asset_name}</h3>
          <p className="text-sm text-slate-600 mt-2 leading-6">{row.reason}</p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 overflow-hidden">
        <div className="grid grid-cols-1 sm:grid-cols-2">
          {detailRows.map(([label, value]) => (
            <div key={label} className="border-b border-slate-100 even:sm:border-l even:sm:border-l-slate-100 p-4 last:border-b-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
              <p className="mt-1 text-sm text-slate-800 break-words">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {stage === 'HR_VERIFICATION' && canHrReview(user.role) ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.hrMut.mutate({ id: row.request_id, is_needed: true })}>Mark needed</button>
          <button type="button" className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.hrMut.mutate({ id: row.request_id, is_needed: false })}>Not needed</button>
          {mutations.hrMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.hrMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'HELPDESK_TRIAGE' && canTriage(user.role) ? (
        <div className="space-y-3 border-t border-slate-100 pt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Triage action</p>
          <div className="flex flex-wrap gap-2">
            <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={triageAction} onChange={(e) => setTriageAction(e.target.value)}>
              <option value="NEW">NEW</option>
              <option value="REPLACE">REPLACE</option>
              <option value="SERVICE">SERVICE</option>
            </select>
            <button type="button" className="rounded-xl bg-indigo-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.triageMut.mutate({ id: row.request_id, action_type: triageAction })}>Apply triage</button>
          </div>
          {mutations.triageMut.isError ? <p className="text-xs text-rose-600">{err(mutations.triageMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'MANAGER_APPROVAL' && canManagerReview(user.role) ? (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-5">
          <button type="button" className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.mgrMut.mutate({ id: row.request_id, is_approved: true })}>Approve</button>
          <button type="button" className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.mgrMut.mutate({ id: row.request_id, is_approved: false })}>Reject</button>
          {mutations.mgrMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.mgrMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'ADMIN_APPROVAL' && canAdminReview(user.role) ? (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-5">
          <button type="button" className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.admMut.mutate({ id: row.request_id, is_approved: true })}>Approve</button>
          <button type="button" className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.admMut.mutate({ id: row.request_id, is_approved: false })}>Reject</button>
          {mutations.admMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.admMut)}</p> : null}
        </div>
      ) : null}

      {canExecuteRequest(user.role) && (stage === 'READY' || row.status === 'APPROVED_FOR_SUPPORT' || row.status === 'READY') ? (
        <div className="space-y-3 border-t border-slate-100 pt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Execute fulfillment</p>
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Provided asset id (AST-123)" value={providedId} onChange={(e) => setProvidedId(e.target.value)} />
          {(row.action_type === 'REPLACE' || row.action_type === 'SERVICE') ? <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Broken / serviced asset id" value={brokenId} onChange={(e) => setBrokenId(e.target.value)} /> : null}
          <button
            type="button"
            className="rounded-xl bg-slate-900 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.execMut.mutate({ id: row.request_id, provided_asset_id: providedId || undefined, broken_asset_id: brokenId || undefined })}
          >
            Execute
          </button>
          {mutations.execMut.isError ? <p className="text-xs text-rose-600">{err(mutations.execMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'IN_REPAIR' && canResolveService(user.role) ? (
        <div className="space-y-3 border-t border-slate-100 pt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Resolve service</p>
          <textarea className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Resolution notes" value={resolveNotes} onChange={(e) => setResolveNotes(e.target.value)} />
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Repair cost" value={repairCost} onChange={(e) => setRepairCost(e.target.value)} />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={disposable} onChange={(e) => setDisposable(e.target.checked)} />
            Asset is non-repairable
          </label>
          <button
            type="button"
            className="rounded-xl bg-teal-700 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.resolveMut.mutate({ id: row.request_id, body: { resolution_notes: resolveNotes, repair_cost: parseFloat(repairCost) || 0, is_disposable: disposable } })}
          >
            Resolve service
          </button>
          {mutations.resolveMut.isError ? <p className="text-xs text-rose-600">{err(mutations.resolveMut)}</p> : null}
        </div>
      ) : null}

      {canTransferCrossBranch(user.role) ? (
        <div className="space-y-3 border-t border-slate-100 pt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Cross-branch transfer</p>
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Target branch" value={tBranch} onChange={(e) => setTBranch(e.target.value)} />
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Target brand" value={tBrand} onChange={(e) => setTBrand(e.target.value)} />
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Target asset name" value={tName} onChange={(e) => setTName(e.target.value)} />
          <button
            type="button"
            className="rounded-xl border border-slate-300 text-sm font-medium px-4 py-2"
            onClick={() => mutations.transferMut.mutate({ id: row.request_id, body: { target_branch: tBranch, target_asset_brand: tBrand, target_asset_name: tName } })}
          >
            Request transfer
          </button>
          {mutations.transferMut.isError ? <p className="text-xs text-rose-600">{err(mutations.transferMut)}</p> : null}
        </div>
      ) : null}
    </div>
  )
}

export default function Requests() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)

  const { data = [], isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['requests'],
    queryFn: () => apiFetch('/requests/'),
  })

  useEffect(() => {
    if (!selectedId && data.length > 0) {
      setSelectedId(data[0].request_id)
    }
    if (selectedId && !data.some((row) => row.request_id === selectedId) && data.length > 0) {
      setSelectedId(data[0].request_id)
    }
  }, [data, selectedId])

  const selected = useMemo(() => data.find((r) => r.request_id === selectedId) ?? null, [data, selectedId])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['requests'] })

  const hrMut = useMutation({ mutationFn: ({ id, is_needed }) => apiFetch(`/requests/${id}/review/hr`, { method: 'POST', body: JSON.stringify({ is_needed }) }), onSuccess: invalidate })
  const triageMut = useMutation({ mutationFn: ({ id, action_type }) => apiFetch(`/requests/${id}/triage`, { method: 'POST', body: JSON.stringify({ action_type }) }), onSuccess: invalidate })
  const mgrMut = useMutation({ mutationFn: ({ id, is_approved }) => apiFetch(`/requests/${id}/review/manager`, { method: 'POST', body: JSON.stringify({ is_approved }) }), onSuccess: invalidate })
  const admMut = useMutation({ mutationFn: ({ id, is_approved }) => apiFetch(`/requests/${id}/review/admin`, { method: 'POST', body: JSON.stringify({ is_approved }) }), onSuccess: invalidate })
  const execMut = useMutation({
    mutationFn: ({ id, provided_asset_id, broken_asset_id }) => {
      const q = new URLSearchParams()
      if (provided_asset_id) q.set('provided_asset_id', provided_asset_id)
      if (broken_asset_id) q.set('broken_asset_id', broken_asset_id)
      const qs = q.toString()
      return apiFetch(`/requests/${id}/execute${qs ? `?${qs}` : ''}`, { method: 'POST' })
    },
    onSuccess: invalidate,
  })
  const resolveMut = useMutation({ mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/resolve`, { method: 'POST', body: JSON.stringify(body) }), onSuccess: invalidate })
  const transferMut = useMutation({ mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/transfer-request`, { method: 'POST', body: JSON.stringify(body) }), onSuccess: invalidate })
  const createMut = useMutation({ mutationFn: (body) => apiFetch('/requests/', { method: 'POST', body: JSON.stringify(body) }), onSuccess: () => invalidate() })

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Requests</h1>
          <p className="text-slate-600 text-sm mt-1">Create requests without needing an exact model name, then review each request with full details.</p>
        </div>
        <button type="button" onClick={() => refetch()} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <NewRequestForm
        busy={createMut.isPending}
        onCreate={(body) => {
          createMut.mutate(body, {
            onSuccess: (row) => {
              if (row?.request_id) setSelectedId(row.request_id)
            },
          })
        }}
      />
      {createMut.isError ? <p className="text-sm text-rose-600">{createMut.error?.message}</p> : null}

      {isLoading ? (
        <div className="py-20 text-center text-slate-400 font-medium animate-pulse">Loading requests…</div>
      ) : isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-800 text-sm">{error?.message}</div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-5 gap-6 items-start">
          <div className="xl:col-span-2">
            <RequestList rows={data} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
          <div className="xl:col-span-3">
            <DetailPanel row={selected} user={user} mutations={{ hrMut, triageMut, mgrMut, admMut, execMut, resolveMut, transferMut }} />
          </div>
        </div>
      )}
    </div>
  )
}



