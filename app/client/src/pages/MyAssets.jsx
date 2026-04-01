import React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'

export default function MyAssets() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const empId = user.employeeId

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['my-assets', empId],
    queryFn: () => apiFetch(`/employees/${empId}/assets`),
    enabled: Boolean(empId),
  })

  const ackMut = useMutation({
    mutationFn: (trackingId) => apiFetch(`/accounts/acknowledge/${encodeURIComponent(trackingId)}`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-assets', empId] }),
  })

  const rows = data?.active_assets ?? []

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
          Confirm receipt of each assignment. This records your acknowledgment in the system (
          <code className="text-xs bg-slate-100 px-1 rounded">POST /accounts/acknowledge/…</code>
          ).
        </p>
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-slate-400 animate-pulse">Loading…</div>
      ) : isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">{error?.message}</div>
      ) : rows.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-slate-200 p-10 text-center text-slate-500 text-sm">No active assets assigned.</p>
      ) : (
        <>
          <p className="text-xs text-slate-500">
            Use <strong>Copy id</strong> if an admin needs the tracking id for a return-to-stock action.
          </p>
          <ul className="space-y-3">
            {rows.map((r) => (
              <li key={r.tracking_id} className="rounded-2xl border border-slate-200 bg-white p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 shadow-sm">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <p className="font-mono text-xs text-slate-500">{r.asset_id}</p>
                    <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
                      {r.allocation_type || 'PERMANENT'}
                    </span>
                    {r.asset?.category && (
                      <span className="text-[10px] font-bold uppercase tracking-wider bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded border border-indigo-100">
                        {r.asset.category}
                      </span>
                    )}
                  </div>
                  
                  <p className="font-bold text-slate-900 text-lg leading-tight">
                    {r.asset?.brand ? `${r.asset.brand} ` : ''}{r.asset?.name || 'Unknown Asset'}
                  </p>
                  
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
        </>
      )}
      {ackMut.isError ? <p className="text-sm text-rose-600">{ackMut.error?.message}</p> : null}
    </div>
  )
}
