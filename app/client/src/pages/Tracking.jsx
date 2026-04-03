import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import { apiFetch } from '@/lib/api'
import { RefreshCw } from 'lucide-react'

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleDateString()
}

function statusBadgeClasses(status) {
  const normalized = (status || '').toUpperCase()
  if (normalized === 'PENDING') return 'bg-amber-50 text-amber-800 border border-amber-200'
  if (normalized === 'APPROVED') return 'bg-emerald-50 text-emerald-800 border border-emerald-200'
  if (normalized === 'REJECTED') return 'bg-rose-50 text-rose-800 border border-rose-200'
  return 'bg-slate-100 text-slate-700 border border-slate-200'
}

function movementBadgeClasses(type) {
  const normalized = (type || '').toUpperCase()
  if (normalized.includes('TRANSFER')) return 'bg-cyan-50 text-cyan-800'
  if (normalized.includes('RETURN')) return 'bg-amber-50 text-amber-800'
  if (normalized.includes('ALLOC')) return 'bg-indigo-50 text-indigo-800'
  if (normalized.includes('SERVICE')) return 'bg-rose-50 text-rose-800'
  return 'bg-slate-100 text-slate-700'
}

function isSoftwareAsset(record) {
  const combined = `${record?.category || ''} ${record?.sub_category || ''} ${record?.asset_name || ''}`.toLowerCase()
  return ['software', 'license', 'subscription', 'saas', 'antivirus', 'office'].some((term) => combined.includes(term))
}

function getApplicableExpiry(record) {
  if (isSoftwareAsset(record)) {
    return {
      label: 'Software License',
      value: record?.license_expiry,
      tone: 'sky',
      helpText: 'Tracks software or license renewal dates linked to this asset.',
    }
  }

  return {
    label: 'Hardware Warranty',
    value: record?.warranty_expiry,
    tone: 'orange',
    helpText: 'Tracks physical device warranty coverage and service expiry.',
  }
}

function DetailItem({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-900">{value || '-'}</p>
    </div>
  )
}

export default function Tracking() {
  const [selectedTrackingId, setSelectedTrackingId] = useState(null)

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['tracking'],
    queryFn: () => apiFetch('/tracking/'),
  })

  const trackingData = data || []
  const selectedRecord =
    trackingData.find((item) => item.tracking_id === selectedTrackingId) ||
    trackingData[0] ||
    null

  const columns = useMemo(
    () => [
      {
        header: 'Asset',
        accessorKey: 'asset_name',
        cell: ({ row }) => (
          <div>
            <p className="font-semibold text-slate-900">{row.original.asset_name || '-'}</p>
            <p className="mt-1 text-xs text-slate-500">{row.original.asset_id || '-'}</p>
          </div>
        ),
      },
      {
        header: 'Movement',
        accessorKey: 'movement_type',
        cell: (c) => (
          <span className={`px-2 py-1 rounded-lg text-xs font-bold uppercase ${movementBadgeClasses(c.getValue())}`}>
            {c.getValue() || '-'}
          </span>
        ),
      },
      {
        header: 'Employee',
        accessorKey: 'emp_id',
        cell: ({ row }) => (
          <div>
            <p className="font-medium text-slate-900">{row.original.emp_id || '-'}</p>
            <p className="mt-1 text-xs text-slate-500">{row.original.allocation_type || '-'}</p>
          </div>
        ),
      },
      {
        header: 'Branch Flow',
        accessorKey: 'branch',
        cell: ({ row }) => {
          const { branch, from_branch: fromBranch, to_branch: toBranch } = row.original
          if (fromBranch || toBranch) {
            return (
              <div>
                <p className="font-medium text-slate-900">{fromBranch || '-'}</p>
                <p className="mt-1 text-xs text-slate-500">to {toBranch || '-'}</p>
              </div>
            )
          }
          return branch || '-'
        },
      },
      {
        header: 'Assigned',
        accessorKey: 'assigned_date',
        cell: (c) => formatDate(c.getValue()),
      },
      {
        header: 'Expiry',
        accessorKey: 'license_expiry',
        cell: ({ row }) => {
          const expiry = getApplicableExpiry(row.original)
          return (
            <div className="min-w-[190px]">
              <div
                className={`rounded-lg px-3 py-2 ${
                  expiry.tone === 'sky'
                    ? 'border border-sky-100 bg-sky-50'
                    : 'border border-orange-100 bg-orange-50'
                }`}
              >
                <p
                  className={`text-[11px] font-semibold uppercase tracking-[0.14em] ${
                    expiry.tone === 'sky' ? 'text-sky-700' : 'text-orange-700'
                  }`}
                >
                  {expiry.label}
                </p>
                <p className="mt-1 text-xs font-medium text-slate-900">{expiry.value || '-'}</p>
              </div>
            </div>
          )
        },
      },
      {
        header: 'Transfer',
        accessorKey: 'transfer_status',
        cell: (c) => {
          const status = c.getValue()
          if (!status) return '-'
          return <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${statusBadgeClasses(status)}`}>{status}</span>
        },
      },
    ],
    [],
  )

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
          <p className="text-sm text-slate-600 mt-1">
            Records follow server-side scope: full for admin and support, branch-wise for manager and HR, and personal history for employees.
          </p>
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
          <div className="p-16 text-center text-slate-400 animate-pulse">Loading tracking...</div>
        ) : isError ? (
          <div className="p-6 text-rose-700 text-sm">{error?.message}</div>
        ) : trackingData.length === 0 ? (
          <div className="p-16 text-center text-slate-500 text-sm">No records in your scope.</div>
        ) : (
          <div className="grid gap-6 xl:grid-cols-[1.35fr_0.95fr]">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm min-w-[1040px]">
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
                  {table.getRowModel().rows.map((row) => {
                    const isSelected = selectedRecord?.tracking_id === row.original.tracking_id
                    return (
                      <tr
                        key={row.id}
                        onClick={() => setSelectedTrackingId(row.original.tracking_id)}
                        className={`cursor-pointer transition-colors ${isSelected ? 'bg-cyan-50/70' : 'hover:bg-slate-50/80'}`}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <td key={cell.id} className="p-4 text-slate-700">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <aside className="border-l border-slate-200 p-6 bg-slate-50/70">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Tracking Detail</p>
                  <h2 className="mt-2 text-xl font-bold text-slate-900">{selectedRecord?.asset_name || 'Select a record'}</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {selectedRecord?.tracking_id || 'Click any row to inspect movement, branch flow, and expiry data.'}
                  </p>
                </div>
                {selectedRecord?.transfer_status ? (
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadgeClasses(selectedRecord.transfer_status)}`}>
                    {selectedRecord.transfer_status}
                  </span>
                ) : null}
              </div>

              {selectedRecord ? (
                <div className="mt-6 space-y-6">
                  {(() => {
                    const expiry = getApplicableExpiry(selectedRecord)
                    return (
                      <>
                        <div className="grid gap-3 sm:grid-cols-2">
                          <DetailItem label="Asset ID" value={selectedRecord.asset_id} />
                          <DetailItem label="Employee" value={selectedRecord.emp_id} />
                          <DetailItem label="Category" value={selectedRecord.category} />
                          <DetailItem label="Sub Category" value={selectedRecord.sub_category} />
                          <DetailItem label="Current Branch" value={selectedRecord.branch} />
                          <DetailItem label="Allocation Type" value={selectedRecord.allocation_type} />
                          <DetailItem label="Movement Type" value={selectedRecord.movement_type} />
                          <DetailItem label="Assigned Date" value={formatDate(selectedRecord.assigned_date)} />
                          <DetailItem label="Returned At" value={formatDate(selectedRecord.returned_at)} />
                          <DetailItem
                            label="Acknowledged"
                            value={selectedRecord.is_acknowledged ? `Yes${selectedRecord.acknowledged_at ? ` on ${formatDate(selectedRecord.acknowledged_at)}` : ''}` : 'No'}
                          />
                        </div>

                        <div>
                          <h3 className="text-sm font-semibold text-slate-900">Branch Flow</h3>
                          <div className="mt-3 grid gap-3 sm:grid-cols-2">
                            <DetailItem label="From Branch" value={selectedRecord.from_branch} />
                            <DetailItem label="To Branch" value={selectedRecord.to_branch} />
                          </div>
                        </div>

                        <div>
                          <h3 className="text-sm font-semibold text-slate-900">Applicable Expiry</h3>
                          <div className="mt-3">
                            <div
                              className={`rounded-2xl px-4 py-4 ${
                                expiry.tone === 'sky'
                                  ? 'border border-sky-100 bg-sky-50'
                                  : 'border border-orange-100 bg-orange-50'
                              }`}
                            >
                              <p
                                className={`text-xs font-semibold uppercase tracking-[0.16em] ${
                                  expiry.tone === 'sky' ? 'text-sky-700' : 'text-orange-700'
                                }`}
                              >
                                {expiry.label} Expiry
                              </p>
                              <p className="mt-2 text-base font-semibold text-slate-900">{expiry.value || '-'}</p>
                              <p className="mt-1 text-sm text-slate-600">{expiry.helpText}</p>
                            </div>
                          </div>
                        </div>

                        <div>
                          <h3 className="text-sm font-semibold text-slate-900">Movement Reason</h3>
                          <div className="mt-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                            {selectedRecord.movement_reason || 'No movement reason recorded.'}
                          </div>
                        </div>
                      </>
                    )
                  })()}
                </div>
              ) : null}
            </aside>
          </div>
        )}
      </div>
    </div>
  )
}
