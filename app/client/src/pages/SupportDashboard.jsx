import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock3, RefreshCw, Wrench } from 'lucide-react'
import { apiFetch } from '@/lib/api'

const TABS = [
  { key: 'PENDING', label: 'Pending' },
  { key: 'IN_SERVICE', label: 'In Service' },
  { key: 'COMPLETED', label: 'Completed' },
  { key: 'SLA_BREACHED', label: 'SLA Breached' },
]

function badgeTone(value) {
  const v = String(value || '').toUpperCase()
  if (v.includes('BREACH') || v.includes('REJECT')) return 'bg-rose-100 text-rose-700 border-rose-200'
  if (v.includes('COMPLETE')) return 'bg-emerald-100 text-emerald-700 border-emerald-200'
  if (v.includes('REPAIR') || v.includes('SERVICE')) return 'bg-amber-100 text-amber-700 border-amber-200'
  return 'bg-slate-100 text-slate-700 border-slate-200'
}

function formatDateTime(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

function isInService(request) {
  const stage = String(request.stage || '').toUpperCase()
  const status = String(request.status || '').toUpperCase()
  return stage === 'IN_REPAIR' || status === 'IN_REPAIR' || status === 'WIP_SERVICE'
}

function isCompleted(request) {
  const stage = String(request.stage || '').toUpperCase()
  const status = String(request.status || '').toUpperCase()
  return stage === 'COMPLETED' || status === 'COMPLETED'
}

function isPending(request) {
  return !isCompleted(request) && !isInService(request)
}

function canAssignNew(request) {
  return String(request.request_type || '').toUpperCase() === 'NEW' && isPending(request)
}

function canStartService(request) {
  const type = String(request.request_type || '').toUpperCase()
  return type === 'SERVICE' && isPending(request)
}

function canCompleteService(request) {
  const type = String(request.request_type || '').toUpperCase()
  return type === 'SERVICE' && isInService(request)
}

function canReplace(request) {
  return String(request.request_type || '').toUpperCase() === 'REPLACE' && isPending(request)
}

function requestActionReason(request, action) {
  if (!request) return 'Select a request first'
  if (action === 'assign_new' && !canAssignNew(request)) return 'Valid only for NEW requests in pending queue'
  if (action === 'start_service' && !canStartService(request)) return 'Valid only for SERVICE requests in pending queue'
  if (action === 'complete_service' && !canCompleteService(request)) return 'Valid only for SERVICE requests in service queue'
  if (action === 'replace' && !canReplace(request)) return 'Valid only for REPLACE requests in pending queue'
  return ''
}

function tabFilter(tab, items) {
  if (tab === 'PENDING') return items.filter(isPending)
  if (tab === 'IN_SERVICE') return items.filter(isInService)
  if (tab === 'COMPLETED') return items.filter(isCompleted)
  if (tab === 'SLA_BREACHED') return items.filter((r) => r.sla_breached)
  return items
}

export default function SupportDashboard() {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState('PENDING')
  const [selectedId, setSelectedId] = useState(null)
  const [providedInstanceId, setProvidedInstanceId] = useState('')
  const [brokenInstanceId, setBrokenInstanceId] = useState('')
  const [oldDisposition, setOldDisposition] = useState('DAMAGED')
  const [issueDescription, setIssueDescription] = useState('')
  const [serviceVendor, setServiceVendor] = useState('')
  const [serviceCost, setServiceCost] = useState('0')
  const [serviceStartDate, setServiceStartDate] = useState('')
  const [expectedReturnDate, setExpectedReturnDate] = useState('')
  const [resolutionNotes, setResolutionNotes] = useState('')
  const [repairCost, setRepairCost] = useState('0')

  const requestsQuery = useQuery({
    queryKey: ['support-dashboard-requests'],
    queryFn: () => apiFetch('/requests?sort_by_status=true&page=1&per_page=300'),
    refetchInterval: 30000,
  })

  const rows = requestsQuery.data?.items || []
  const visibleRows = useMemo(() => tabFilter(activeTab, rows), [activeTab, rows])
  const selected = useMemo(() => visibleRows.find((r) => r.request_id === selectedId) || rows.find((r) => r.request_id === selectedId) || null, [visibleRows, rows, selectedId])

  const invalidate = () => qc.invalidateQueries({ queryKey: ['support-dashboard-requests'] })

  const assignNewMut = useMutation({
    mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/support/assign-new`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidate,
  })
  const replaceMut = useMutation({
    mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/support/replace`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidate,
  })
  const startServiceMut = useMutation({
    mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/support/service/start`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidate,
  })
  const completeServiceMut = useMutation({
    mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/support/service/complete`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidate,
  })

  const anyBusy = assignNewMut.isPending || replaceMut.isPending || startServiceMut.isPending || completeServiceMut.isPending

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Support Dashboard</h1>
          <p className="text-sm text-slate-600 mt-1">Queue-driven support workflow with SLA visibility and valid-action controls.</p>
        </div>
        <button
          type="button"
          onClick={() => requestsQuery.refetch()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <RefreshCw className={`w-4 h-4 ${requestsQuery.isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-2 flex flex-wrap gap-2">
        {TABS.map((tab) => {
          const count = tabFilter(tab.key, rows).length
          const active = activeTab === tab.key
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-xl px-4 py-2 text-sm font-semibold border ${active ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'}`}
            >
              {tab.label} ({count})
            </button>
          )
        })}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-6">
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
          <div className="grid grid-cols-[1fr_1fr_1fr_.8fr_.9fr_.8fr_1.1fr] gap-3 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500 border-b border-slate-100">
            <span>request_id</span>
            <span>employee</span>
            <span>asset</span>
            <span>type</span>
            <span>status</span>
            <span>priority</span>
            <span>sla_due</span>
          </div>

          <div className="divide-y divide-slate-100 max-h-[66vh] overflow-auto">
            {requestsQuery.isLoading ? (
              <p className="p-4 text-sm text-slate-500">Loading requests...</p>
            ) : visibleRows.length === 0 ? (
              <p className="p-4 text-sm text-slate-500">No requests in this queue.</p>
            ) : (
              visibleRows.map((row) => {
                const selectedRow = selectedId === row.request_id
                return (
                  <button
                    key={row.request_id}
                    type="button"
                    onClick={() => {
                      setSelectedId(row.request_id)
                      setProvidedInstanceId('')
                      setBrokenInstanceId(row.instance_id || '')
                      setIssueDescription(row.service_issue_description || row.reason || '')
                      setServiceVendor(row.service_vendor || '')
                      setServiceCost(row.service_cost != null ? String(row.service_cost) : '0')
                      setServiceStartDate('')
                      setExpectedReturnDate(row.expected_return_date ? new Date(row.expected_return_date).toISOString().slice(0, 16) : '')
                      setResolutionNotes('')
                      setRepairCost(row.service_cost != null ? String(row.service_cost) : '0')
                    }}
                    className={`w-full text-left grid grid-cols-[1fr_1fr_1fr_.8fr_.9fr_.8fr_1.1fr] gap-3 px-4 py-3 text-sm ${selectedRow ? 'bg-cyan-50' : 'bg-white hover:bg-slate-50'}`}
                  >
                    <span className="font-mono text-slate-700 truncate">{row.request_id}</span>
                    <span className="truncate">{row.requester_name || row.emp_id}</span>
                    <span className="truncate">{row.asset_name}</span>
                    <span>{row.request_type}</span>
                    <span>
                      <span className={`inline-flex items-center rounded-lg border px-2 py-0.5 text-xs font-semibold ${badgeTone(row.status)}`}>{row.status}</span>
                    </span>
                    <span>{row.priority || '-'}</span>
                    <span className={row.sla_breached ? 'text-rose-700 font-semibold' : ''}>{formatDateTime(row.sla_due || row.sla_target_at)}</span>
                  </button>
                )
              })
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900">Action Panel</h2>
            {selected?.sla_breached ? (
              <span className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2 py-1 text-xs font-semibold text-rose-700">
                <AlertTriangle className="w-3.5 h-3.5" /> SLA Breached
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
                <Clock3 className="w-3.5 h-3.5" /> Within SLA
              </span>
            )}
          </div>

          {!selected ? (
            <p className="text-sm text-slate-500">Select a request from the table to view valid actions.</p>
          ) : (
            <>
              <div className="rounded-xl border border-slate-200 p-3 text-sm space-y-1">
                <p><span className="text-slate-500">Request:</span> {selected.request_id}</p>
                <p><span className="text-slate-500">Type:</span> {selected.request_type}</p>
                <p><span className="text-slate-500">Status:</span> {selected.status}</p>
                <p><span className="text-slate-500">Employee:</span> {selected.requester_name || selected.emp_id}</p>
              </div>

              {String(selected.request_type).toUpperCase() === 'NEW' ? (
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Assign Asset</label>
                  <input
                    className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                    placeholder="Provided instance id"
                    value={providedInstanceId}
                    onChange={(e) => setProvidedInstanceId(e.target.value)}
                  />
                  <button
                    type="button"
                    disabled={!canAssignNew(selected) || !providedInstanceId.trim() || anyBusy}
                    onClick={() => assignNewMut.mutate({ id: selected.request_id, body: { provided_instance_id: providedInstanceId.trim() } })}
                    className="w-full rounded-xl bg-slate-900 text-white px-4 py-2 text-sm font-semibold disabled:opacity-50"
                  >
                    {assignNewMut.isPending ? 'Assigning...' : 'Assign asset'}
                  </button>
                  {!canAssignNew(selected) ? <p className="text-xs text-amber-700">{requestActionReason(selected, 'assign_new')}</p> : null}
                </div>
              ) : null}

              {String(selected.request_type).toUpperCase() === 'SERVICE' ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Start Service</label>
                    <textarea
                      className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                      rows={2}
                      placeholder="Issue description"
                      value={issueDescription}
                      onChange={(e) => setIssueDescription(e.target.value)}
                    />
                    <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Service vendor" value={serviceVendor} onChange={(e) => setServiceVendor(e.target.value)} />
                    <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Service cost" value={serviceCost} onChange={(e) => setServiceCost(e.target.value)} />
                    <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Broken instance id" value={brokenInstanceId} onChange={(e) => setBrokenInstanceId(e.target.value)} />
                    <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Temporary instance id (optional)" value={providedInstanceId} onChange={(e) => setProvidedInstanceId(e.target.value)} />
                    <div className="grid grid-cols-2 gap-2">
                      <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" type="datetime-local" value={serviceStartDate} onChange={(e) => setServiceStartDate(e.target.value)} />
                      <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" type="datetime-local" value={expectedReturnDate} onChange={(e) => setExpectedReturnDate(e.target.value)} />
                    </div>
                    <button
                      type="button"
                      disabled={!canStartService(selected) || !issueDescription.trim() || !brokenInstanceId.trim() || anyBusy}
                      onClick={() => startServiceMut.mutate({
                        id: selected.request_id,
                        body: {
                          issue_description: issueDescription.trim(),
                          service_vendor: serviceVendor.trim() || undefined,
                          service_cost: parseFloat(serviceCost) || 0,
                          service_start_date: serviceStartDate ? new Date(serviceStartDate).toISOString() : new Date().toISOString(),
                          expected_return_date: expectedReturnDate ? new Date(expectedReturnDate).toISOString() : undefined,
                          broken_instance_id: brokenInstanceId.trim(),
                          temporary_instance_id: providedInstanceId.trim() || undefined,
                        },
                      })}
                      className="w-full rounded-xl bg-amber-600 text-white px-4 py-2 text-sm font-semibold disabled:opacity-50"
                    >
                      {startServiceMut.isPending ? 'Starting...' : 'Start service'}
                    </button>
                    {!canStartService(selected) ? <p className="text-xs text-amber-700">{requestActionReason(selected, 'start_service')}</p> : null}
                  </div>

                  <div className="space-y-2 border-t border-slate-100 pt-4">
                    <label className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Complete Service</label>
                    <textarea className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" rows={2} placeholder="Resolution notes" value={resolutionNotes} onChange={(e) => setResolutionNotes(e.target.value)} />
                    <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Repair cost" value={repairCost} onChange={(e) => setRepairCost(e.target.value)} />
                    <button
                      type="button"
                      disabled={!canCompleteService(selected) || !resolutionNotes.trim() || anyBusy}
                      onClick={() => completeServiceMut.mutate({
                        id: selected.request_id,
                        body: {
                          resolution_notes: resolutionNotes.trim(),
                          repair_cost: parseFloat(repairCost) || 0,
                          repaired_instance_id: brokenInstanceId.trim() || undefined,
                        },
                      })}
                      className="w-full rounded-xl bg-emerald-700 text-white px-4 py-2 text-sm font-semibold disabled:opacity-50"
                    >
                      {completeServiceMut.isPending ? 'Completing...' : 'Complete service'}
                    </button>
                    {!canCompleteService(selected) ? <p className="text-xs text-amber-700">{requestActionReason(selected, 'complete_service')}</p> : null}
                  </div>
                </div>
              ) : null}

              {String(selected.request_type).toUpperCase() === 'REPLACE' ? (
                <div className="space-y-2">
                  <label className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Replace Asset</label>
                  <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Replacement instance id" value={providedInstanceId} onChange={(e) => setProvidedInstanceId(e.target.value)} />
                  <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Broken instance id" value={brokenInstanceId} onChange={(e) => setBrokenInstanceId(e.target.value)} />
                  <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={oldDisposition} onChange={(e) => setOldDisposition(e.target.value)}>
                    <option value="DAMAGED">Mark old asset damaged</option>
                    <option value="RETIRED">Retire old asset</option>
                  </select>
                  <button
                    type="button"
                    disabled={!canReplace(selected) || !providedInstanceId.trim() || anyBusy}
                    onClick={() => replaceMut.mutate({
                      id: selected.request_id,
                      body: {
                        provided_instance_id: providedInstanceId.trim(),
                        broken_instance_id: brokenInstanceId.trim() || undefined,
                        old_asset_disposition: oldDisposition,
                      },
                    })}
                    className="w-full rounded-xl bg-indigo-700 text-white px-4 py-2 text-sm font-semibold disabled:opacity-50"
                  >
                    {replaceMut.isPending ? 'Replacing...' : 'Replace asset'}
                  </button>
                  {!canReplace(selected) ? <p className="text-xs text-amber-700">{requestActionReason(selected, 'replace')}</p> : null}
                </div>
              ) : null}

              {assignNewMut.isError ? <p className="text-xs text-rose-600">{assignNewMut.error?.message}</p> : null}
              {replaceMut.isError ? <p className="text-xs text-rose-600">{replaceMut.error?.message}</p> : null}
              {startServiceMut.isError ? <p className="text-xs text-rose-600">{startServiceMut.error?.message}</p> : null}
              {completeServiceMut.isError ? <p className="text-xs text-rose-600">{completeServiceMut.error?.message}</p> : null}

              {(assignNewMut.isSuccess || replaceMut.isSuccess || startServiceMut.isSuccess || completeServiceMut.isSuccess) ? (
                <p className="inline-flex items-center gap-2 text-xs text-emerald-700 font-medium">
                  <CheckCircle2 className="w-4 h-4" /> Action completed and queue refreshed.
                </p>
              ) : null}
            </>
          )}

          <div className="text-xs text-slate-500 border-t border-slate-100 pt-3 flex items-center gap-2">
            <Wrench className="w-3.5 h-3.5" />
            Only valid actions are enabled; form values auto-fill from selected request.
          </div>
        </div>
      </div>
    </div>
  )
}
