import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import { RefreshCw } from 'lucide-react'

export default function Finance() {
  const { user } = useAuth()
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['finance', user.branch],
    queryFn: () => apiFetch(`/accounts/summary${user.branch ? `?branch=${encodeURIComponent(user.branch)}` : ''}`),
  })

  const cards = data
    ? [
        { label: 'Total asset value', value: data.total_asset_value, format: 'currency' },
        { label: 'Maintenance overhead', value: data.total_maintenance_overhead, format: 'currency' },
        { label: 'Unused asset value', value: data.unused_asset_value, format: 'currency' },
        { label: 'Asset records', value: data.asset_count, format: 'int' },
        { label: 'Stock lines', value: data.stock_count, format: 'int' },
      ]
    : []

  return (
    <div className="p-6 sm:p-8 max-w-5xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Finance</h1>
          <p className="text-sm text-slate-600 mt-1">Summary from <code className="text-xs bg-slate-100 px-1 rounded">GET /accounts/summary</code></p>
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

      {isLoading ? (
        <div className="py-20 text-center text-slate-400 animate-pulse">Loading summary…</div>
      ) : isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">{error?.message}</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {cards.map(({ label, value, format }) => (
            <div key={label} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
              <p className="text-2xl font-bold text-slate-900 mt-3 tabular-nums">
                {format === 'currency'
                  ? Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })
                  : Number(value).toLocaleString()}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
