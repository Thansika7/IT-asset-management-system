import React, { useMemo, useState } from 'react'
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
import { Plus, RefreshCw } from 'lucide-react'

function Badge({ children, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
    amber: 'bg-amber-50 text-amber-800 border-amber-200',
    emerald: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rose: 'bg-rose-50 text-rose-800 border-rose-200',
    violet: 'bg-violet-50 text-violet-800 border-violet-200',
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
  return 'violet'
}

function NewRequestForm({ onCreate, busy }) {
  const [asset_name, setAssetName] = useState('')
  const [asset_category, setCategory] = useState('')
  const [reason, setReason] = useState('')
  const [action_type, setActionType] = useState('NEW')

  const submit = (e) => {
    e.preventDefault()
    onCreate({ asset_name, asset_category, reason, action_type })
    setAssetName('')
    setCategory('')
    setReason('')
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4 shadow-sm">
      <h3 className="font-bold text-slate-900">New request</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input
          required
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
          placeholder="Asset name"
          value={asset_name}
          onChange={(e) => setAssetName(e.target.value)}
        />
        <input
          required
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
          placeholder="Category (e.g. Laptop)"
          value={asset_category}
          onChange={(e) => setAssetCategory(e.target.value)}
        />
      </div>
      <textarea
        required
        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm min-h-[88px]"
        placeholder="Reason / context"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <div className="flex flex-wrap gap-3 items-center">
        <label className="text-xs font-semibold text-slate-600">Request type</label>
        <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={action_type} onChange={(e) => setActionType(e.target.value)}>
          <option value="NEW">New allocation</option>
          <option value="REPLACE">Replace asset</option>
          <option value="SERVICE">Service / repair</option>
        </select>
        <button
          type="submit"
          disabled={busy}
          className="ml-auto inline-flex items-center gap-2 rounded-xl bg-slate-900 text-white text-sm font-semibold px-4 py-2 disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          Submit
        </button>
      </div>
    </form>
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

  if (!row) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/80 p-8 text-center text-slate-500 text-sm">
        Select a request to see details and available actions.
      </div>
    )
  }

  const stage = row.stage
  const err = (m) => m.error?.message || m.error?.data?.message

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-5">
      <div>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{row.request_id}</p>
        <h3 className="text-lg font-bold text-slate-900 mt-1">{row.asset_name}</h3>
        <p className="text-sm text-slate-600 mt-2">{row.reason}</p>
        <div className="flex flex-wrap gap-2 mt-3">
          <Badge tone={stageTone(stage)}>{stage || '—'}</Badge>
          <Badge>{row.status}</Badge>
          {row.action_type ? <Badge tone="slate">action: {row.action_type}</Badge> : null}
        </div>
      </div>

      {stage === 'HR_VERIFICATION' && canHrReview(user.role) ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.hrMut.mutate({ id: row.request_id, is_needed: true })}
          >
            Mark needed
          </button>
          <button
            type="button"
            className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.hrMut.mutate({ id: row.request_id, is_needed: false })}
          >
            Not needed
          </button>
          {mutations.hrMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.hrMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'HELPDESK_TRIAGE' && canTriage(user.role) ? (
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-600">Triage action</label>
          <div className="flex flex-wrap gap-2">
            <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={triageAction} onChange={(e) => setTriageAction(e.target.value)}>
              <option value="NEW">NEW</option>
              <option value="REPLACE">REPLACE</option>
              <option value="SERVICE">SERVICE</option>
            </select>
            <button
              type="button"
              className="rounded-xl bg-indigo-600 text-white text-sm font-medium px-4 py-2"
              onClick={() => mutations.triageMut.mutate({ id: row.request_id, action_type: triageAction })}
            >
              Apply triage
            </button>
          </div>
          {mutations.triageMut.isError ? <p className="text-xs text-rose-600">{err(mutations.triageMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'MANAGER_APPROVAL' && canManagerReview(user.role) ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.mgrMut.mutate({ id: row.request_id, is_approved: true })}
          >
            Approve
          </button>
          <button
            type="button"
            className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.mgrMut.mutate({ id: row.request_id, is_approved: false })}
          >
            Reject
          </button>
          {mutations.mgrMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.mgrMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'ADMIN_APPROVAL' && canAdminReview(user.role) ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.admMut.mutate({ id: row.request_id, is_approved: true })}
          >
            Approve
          </button>
          <button
            type="button"
            className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.admMut.mutate({ id: row.request_id, is_approved: false })}
          >
            Reject
          </button>
          {mutations.admMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.admMut)}</p> : null}
        </div>
      ) : null}

      {canExecuteRequest(user.role) &&
      (stage === 'READY' || row.status === 'APPROVED_FOR_SUPPORT' || row.status === 'READY') ? (
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <p className="text-xs font-semibold text-slate-600">Execute fulfillment</p>
          <input
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Provided asset id (AST-…)"
            value={providedId}
            onChange={(e) => setProvidedId(e.target.value)}
          />
          {(row.action_type === 'REPLACE' || row.action_type === 'SERVICE') && (
            <input
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
              placeholder="Broken / serviced asset id"
              value={brokenId}
              onChange={(e) => setBrokenId(e.target.value)}
            />
          )}
          <button
            type="button"
            className="rounded-xl bg-slate-900 text-white text-sm font-medium px-4 py-2"
            onClick={() =>
              mutations.execMut.mutate({
                id: row.request_id,
                provided_asset_id: providedId || undefined,
                broken_asset_id: brokenId || undefined,
              })
            }
          >
            Execute
          </button>
          {mutations.execMut.isError ? <p className="text-xs text-rose-600">{err(mutations.execMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'IN_REPAIR' && canResolveService(user.role) ? (
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <textarea
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Resolution notes"
            value={resolveNotes}
            onChange={(e) => setResolveNotes(e.target.value)}
          />
          <input
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Repair cost"
            value={repairCost}
            onChange={(e) => setRepairCost(e.target.value)}
          />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={disposable} onChange={(e) => setDisposable(e.target.checked)} />
            Asset is non-repairable (retire)
          </label>
          <button
            type="button"
            className="rounded-xl bg-teal-700 text-white text-sm font-medium px-4 py-2"
            onClick={() =>
              mutations.resolveMut.mutate({
                id: row.request_id,
                body: {
                  resolution_notes: resolveNotes,
                  repair_cost: parseFloat(repairCost) || 0,
                  is_disposable: disposable,
                },
              })
            }
          >
            Resolve service
          </button>
          {mutations.resolveMut.isError ? <p className="text-xs text-rose-600">{err(mutations.resolveMut)}</p> : null}
        </div>
      ) : null}

      {canTransferCrossBranch(user.role) ? (
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <p className="text-xs font-semibold text-slate-600">Cross-branch transfer (manager)</p>
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Target branch" value={tBranch} onChange={(e) => setTBranch(e.target.value)} />
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Target brand" value={tBrand} onChange={(e) => setTBrand(e.target.value)} />
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Target asset name" value={tName} onChange={(e) => setTName(e.target.value)} />
          <button
            type="button"
            className="rounded-xl border border-slate-300 text-sm font-medium px-4 py-2"
            onClick={() =>
              mutations.transferMut.mutate({
                id: row.request_id,
                body: {
                  target_branch: tBranch,
                  target_asset_brand: tBrand,
                  target_asset_name: tName,
                },
              })
            }
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

  const selected = useMemo(() => data.find((r) => r.request_id === selectedId) ?? null, [data, selectedId])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['requests'] })

  const hrMut = useMutation({
    mutationFn: ({ id, is_needed }) => apiFetch(`/requests/${id}/review/hr`, { method: 'POST', body: JSON.stringify({ is_needed }) }),
    onSuccess: invalidate,
  })

  const triageMut = useMutation({
    mutationFn: ({ id, action_type }) => apiFetch(`/requests/${id}/triage`, { method: 'POST', body: JSON.stringify({ action_type }) }),
    onSuccess: invalidate,
  })

  const mgrMut = useMutation({
    mutationFn: ({ id, is_approved }) => apiFetch(`/requests/${id}/review/manager`, { method: 'POST', body: JSON.stringify({ is_approved }) }),
    onSuccess: invalidate,
  })

  const admMut = useMutation({
    mutationFn: ({ id, is_approved }) => apiFetch(`/requests/${id}/review/admin`, { method: 'POST', body: JSON.stringify({ is_approved }) }),
    onSuccess: invalidate,
  })

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

  const resolveMut = useMutation({
    mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/resolve`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidate,
  })

  const transferMut = useMutation({
    mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/transfer-request`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidate,
  })

  const createMut = useMutation({
    mutationFn: (body) => apiFetch('/requests/', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidate(),
  })

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Requests</h1>
          <p className="text-slate-600 text-sm mt-1">Lifecycle matches the FastAPI workflow; actions appear based on your role and stage.</p>
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
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
          <div className="lg:col-span-2 space-y-2">
            {data.length === 0 ? (
              <p className="text-sm text-slate-500 py-8 text-center border border-dashed border-slate-200 rounded-2xl">No requests yet.</p>
            ) : (
              data.map((row) => (
                <button
                  key={row.request_id}
                  type="button"
                  onClick={() => setSelectedId(row.request_id)}
                  className={`w-full text-left rounded-2xl border px-4 py-3 transition-all ${
                    selectedId === row.request_id ? 'border-teal-400 bg-teal-50/50 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-900 text-sm truncate">{row.asset_name}</span>
                    <Badge tone={stageTone(row.stage)}>{row.stage}</Badge>
                  </div>
                  <p className="text-xs text-slate-500 mt-1 font-mono">{row.request_id}</p>
                </button>
              ))
            )}
          </div>
          <div className="lg:col-span-3">
            <DetailPanel
              row={selected}
              user={user}
              mutations={{ hrMut, triageMut, mgrMut, admMut, execMut, resolveMut, transferMut }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
