import React, { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import { apiFetch } from '@/lib/api'
import Pagination from '@/components/Pagination'
import { RefreshCw, Activity } from 'lucide-react'

export default function AssetUsage() {
  const [selectedId, setSelectedId] = useState(null)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 10

  const {
    data: analytics,
    isLoading: aLoad,
    isError: aErr,
    error: aError,
    refetch: refetchA,
    isFetching: aFetch,
  } = useQuery({
    queryKey: ['asset-usage-analytics'],
    queryFn: () => apiFetch('/assets/usage/analytics'),
  })

  const {
    data: report,
    isLoading: rLoad,
    isError: rErr,
    error: rError,
    refetch: refetchR,
    isFetching: rFetch,
  } = useQuery({
    queryKey: ['asset-usage-report'],
    queryFn: () => apiFetch('/assets/usage/report'),
  })

  const {
    data: detail,
    isLoading: dLoad,
    isError: dErr,
    error: dError,
  } = useQuery({
    queryKey: ['asset-usage-detail', selectedId],
    queryFn: () => apiFetch(`/assets/${selectedId}/usage`),
    enabled: Boolean(selectedId),
  })

  const items = report?.items ?? []
  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE))
  const pagedItems = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return items.slice(start, start + PAGE_SIZE)
  }, [items, page])
  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  const columns = useMemo(
    () => [
      { header: 'Asset ID', accessorKey: 'asset_id', cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> },
      { header: 'Name', accessorKey: 'name', cell: (c) => <span className="font-semibold text-slate-800">{c.getValue()}</span> },
      { header: 'Branch', accessorKey: 'branch', cell: (c) => c.getValue() || '—' },
      { header: 'Used / Avail.', accessorKey: 'used', cell: ({ row }) => `${row.original.used} / ${row.original.unused}` },
      { header: 'Tracking rows', accessorKey: 'allocation_events' },
      { header: 'Repairs (cat.)', accessorKey: 'repair_count' },
    ],
    [],
  )

  const table = useReactTable({
    data: pagedItems,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const busy = aLoad || rLoad
  const fetching = aFetch || rFetch

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Activity className="w-7 h-7 text-teal-600" />
            Asset usage
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Built from <code className="text-xs bg-slate-100 px-1 rounded">Tracking</code> movements and catalog fields (
            <code className="text-xs bg-slate-100 px-1 rounded">GET /assets/usage/analytics</code>,{' '}
            <code className="text-xs bg-slate-100 px-1 rounded">GET /assets/usage/report</code>,{' '}
            <code className="text-xs bg-slate-100 px-1 rounded">GET /assets/:id/usage</code>). Branch-scoped for managers, HR, and support.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            refetchA()
            refetchR()
          }}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <RefreshCw className={`w-4 h-4 ${fetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {aErr ? <p className="text-sm text-rose-600">{aError?.message}</p> : null}
      {rErr ? <p className="text-sm text-rose-600">{rError?.message}</p> : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Tracking events (scope)" value={analytics?.total_tracking_events} loading={busy} />
        <MetricCard label="Sum repair count (catalog)" value={analytics?.sum_repair_count_catalog} loading={busy} />
        <MetricCard label="Rows in report" value={report?.count} loading={busy} />
        <MetricCard label="Report branch filter" value={report?.branch ?? 'All'} loading={busy} isText />
      </div>

      {analytics?.events_by_movement_type ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold text-slate-800 mb-3">Events by movement type</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-sm">
            {Object.entries(analytics.events_by_movement_type).map(([k, v]) => (
              <div key={k} className="flex justify-between rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                <span className="text-slate-600 font-mono text-xs">{k}</span>
                <span className="font-semibold text-slate-900">{v}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
          {busy ? (
            <div className="p-16 text-center text-slate-400 animate-pulse">Loading report…</div>
          ) : (
            <div className="min-w-0 flex flex-col">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm min-w-[640px]">
                  <thead>
                    {table.getHeaderGroups().map((hg) => (
                      <tr key={hg.id} className="bg-slate-50 border-b border-slate-200">
                        {hg.headers.map((h) => (
                          <th
                            key={h.id}
                            className="p-3 font-semibold text-slate-600 text-xs uppercase tracking-wider cursor-pointer"
                            onClick={h.column.getToggleSortingHandler()}
                          >
                            {flexRender(h.column.columnDef.header, h.getContext())}
                          </th>
                        ))}
                      </tr>
                    ))}
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {table.getRowModel().rows.map((row) => {
                      const id = row.original.asset_id
                      const active = selectedId === id
                      return (
                        <tr
                          key={row.id}
                          onClick={() => setSelectedId(id)}
                          className={`cursor-pointer hover:bg-slate-50/80 ${active ? 'bg-teal-50/80' : ''}`}
                        >
                          {row.getVisibleCells().map((cell) => (
                            <td key={cell.id} className="p-3">
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </td>
                          ))}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {items.length === 0 ? <p className="p-6 text-sm text-slate-500 text-center">No assets in scope.</p> : null}
              </div>
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={items.length} />
            </div>
          )}
        </div>

        <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4 min-h-[280px]">
          {!selectedId ? (
            <p className="text-sm text-slate-500">Select a row for per-asset usage: allocation / repair / transfer history and duration metrics.</p>
          ) : dLoad ? (
            <p className="text-sm text-slate-400 animate-pulse">Loading detail…</p>
          ) : dErr ? (
            <p className="text-sm text-rose-600">{dError?.message}</p>
          ) : detail ? (
            <>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Asset</p>
                <p className="text-lg font-bold text-slate-900">{detail.name}</p>
                <p className="font-mono text-xs text-slate-500">{detail.asset_id}</p>
                <p className="text-xs text-slate-600 mt-1">
                  {detail.category || '—'} · {detail.branch || '—'}
                </p>
              </div>
              {detail.metrics ? (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <MetricMini label="Usage hrs" value={detail.metrics.usage_duration_hours} />
                  <MetricMini label="Downtime hrs" value={detail.metrics.downtime_hours} />
                  <MetricMini label="Allocations" value={detail.metrics.allocation_count} />
                  <MetricMini label="Idle units" value={detail.metrics.idle_units} />
                  <MetricMini label="Repairs" value={detail.metrics.repair_count} />
                </div>
              ) : null}
              <HistorySnippet title="Recent allocations" rows={detail.allocation_history} />
              <HistorySnippet title="Recent repairs" rows={detail.repair_history} />
            </>
          ) : null}
        </aside>
      </div>
    </div>
  )
}

function MetricCard({ label, value, loading, isText }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-bold text-slate-900">
        {loading ? '…' : isText ? String(value ?? '—') : value ?? 0}
      </p>
    </div>
  )
}

function MetricMini({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-2 py-1.5">
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className="font-semibold text-slate-800">{value ?? '—'}</p>
    </div>
  )
}

function HistorySnippet({ title, rows }) {
  const list = Array.isArray(rows) ? rows.slice(-5) : []
  return (
    <div>
      <p className="text-xs font-bold text-slate-700 mb-2">{title}</p>
      {list.length === 0 ? (
        <p className="text-[11px] text-slate-400">No entries.</p>
      ) : (
        <ul className="space-y-1.5 text-[11px] text-slate-600 max-h-32 overflow-y-auto">
          {list.map((r) => (
            <li key={r.tracking_id} className="border-b border-slate-100 pb-1">
              <span className="font-mono text-slate-500">{r.tracking_id}</span> · {r.movement_type || '—'} · emp {r.emp_id || '—'}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
