import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'

export default function MyAssets() {
  const { user } = useAuth()
  const empId = user.employeeId

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['my-assets', empId],
    queryFn: () => apiFetch(`/employees/${empId}/assets`),
    enabled: Boolean(empId),
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
        <p className="text-sm text-slate-600 mt-1">Active assignments from your profile.</p>
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
            Use the tracking id for admin return-to-stock (<strong>Inventory → Return / recover</strong>).
          </p>
          <ul className="space-y-3">
            {rows.map((r) => (
              <li key={r.tracking_id} className="rounded-2xl border border-slate-200 bg-white p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 shadow-sm">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-mono text-xs text-slate-600">{r.tracking_id}</p>
                    <button
                      type="button"
                      className="text-xs font-semibold text-teal-700 hover:underline"
                      onClick={() => navigator.clipboard.writeText(r.tracking_id)}
                    >
                      Copy id
                    </button>
                  </div>
                  <p className="font-semibold text-slate-900 mt-1">Asset {r.asset_id}</p>
                </div>
                <span
                  className={`text-xs font-bold uppercase px-2 py-1 rounded-lg self-start ${
                    r.is_acknowledged ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'
                  }`}
                >
                  {r.is_acknowledged ? 'Acknowledged' : 'Pending ack'}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
