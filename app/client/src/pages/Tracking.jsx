import React, { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import { apiFetch } from '@/lib/api'
import { RefreshCw } from 'lucide-react'

export default function Tracking() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['tracking'],
    queryFn: () => apiFetch('/tracking/'),
  })

  const columns = useMemo(
    () => [
      { header: 'Asset', accessorKey: 'asset_name', cell: (c) => c.getValue() || '—' },
      {
        header: 'Movement',
        accessorKey: 'movement_type',
        cell: (c) => (
          <span className="px-2 py-1 rounded-lg text-xs font-bold uppercase bg-indigo-50 text-indigo-800">{c.getValue() || '—'}</span>
        ),
      },
      { header: 'Branch', accessorKey: 'branch', cell: (c) => c.getValue() || '—' },
      {
        header: 'Assigned',
        accessorKey: 'assigned_date',
        cell: (c) => {
          const v = c.getValue()
          return v ? new Date(v).toLocaleDateString() : '—'
        },
      },
      {
        header: 'Transfer',
        accessorKey: 'transfer_status',
        cell: (c) => {
          const s = c.getValue()
          if (!s) return '—'
          const colors = {
            PENDING: 'bg-amber-50 text-amber-800',
            APPROVED: 'bg-emerald-50 text-emerald-800',
            REJECTED: 'bg-rose-50 text-rose-800',
          }
          return <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${colors[s] || 'bg-slate-100 text-slate-700'}`}>{s}</span>
        },
      },
    ],
    [],
  )

  const trackingData = data || []
  const table = useReactTable({
    data: trackingData,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Tracking</h1>
          <p className="text-sm text-slate-600 mt-1">Records respect server-side scope (full for admin/support; personal for others).</p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:shadow-md hover:-translate-y-0.5 active:translate-y-0 transition-all cursor-pointer"
        >
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-16 text-center text-slate-400 animate-pulse">Loading tracking…</div>
        ) : isError ? (
          <div className="p-6 text-rose-700 text-sm">{error?.message}</div>
        ) : trackingData.length === 0 ? (
          <div className="p-16 text-center text-slate-500 text-sm">No records in your scope.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm min-w-[800px]">
              <thead>
                {table.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id} className="bg-slate-50 border-b border-slate-200">
                    {headerGroup.headers.map((header) => (
                      <th
                        key={header.id}
                        className="p-4 text-xs font-semibold text-slate-600 uppercase tracking-wider cursor-pointer"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="divide-y divide-slate-100">
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-50/80">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="p-4 text-slate-700">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
