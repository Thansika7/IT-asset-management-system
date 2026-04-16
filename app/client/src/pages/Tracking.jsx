import React, { useMemo, useState } from 'react'
import Pagination from '@/components/Pagination'
import { useQuery } from '@tanstack/react-query'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import { apiFetch } from '@/lib/api'
import { normalizeOptions } from '@/lib/options'
import { RefreshCw } from 'lucide-react'

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleDateString()
}

function statusBadgeClasses(status) {
  const normalized = (status || '').toUpperCase()
  if (normalized === 'NEW') return 'bg-sky-50 text-sky-800 border border-sky-200'
  if (normalized === 'ASSIGNED') return 'bg-indigo-50 text-indigo-800 border border-indigo-200'
  if (normalized === 'RETURNED') return 'bg-emerald-50 text-emerald-800 border border-emerald-200'
  if (normalized === 'IN_REPAIR') return 'bg-amber-50 text-amber-800 border border-amber-200'
  if (normalized === 'NOT_USABLE') return 'bg-rose-50 text-rose-800 border border-rose-200'
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
      label: 'Software Expiry',
      value: record?.license_expiry,
      tone: 'sky',
      helpText: 'Tracks software license or subscription renewal dates linked to this asset.',
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
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 12
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [branchId, setBranchId] = useState('')
  const [employeeId, setEmployeeId] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [movementType, setMovementType] = useState('')
  const [transferStatus, setTransferStatus] = useState('')

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      per_page: String(PAGE_SIZE),
    })
    if (search.trim()) params.set('search', search.trim())
    if (status) params.set('status', status)
    if (branchId) params.set('branch_id', branchId)
    if (employeeId) params.set('employee_id', employeeId)
    if (categoryId) params.set('category_id', categoryId)
    if (movementType) params.set('movement_type', movementType)
    if (transferStatus) params.set('transfer_status', transferStatus)
    return params.toString()
  }, [page, search, status, branchId, employeeId, categoryId, movementType, transferStatus])

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['tracking', queryString],
    queryFn: () => apiFetch(`/tracking/?${queryString}`),
  })

  const { data: options } = useQuery({
    queryKey: ['tracking-options'],
    queryFn: () => apiFetch('/tracking/options'),
  })

  const statusOptions = options?.statuses || []
  const branchOptions = normalizeOptions(options?.branches || [])
  const employeeOptions = normalizeOptions(options?.employees || [])
  const categoryOptions = normalizeOptions(options?.categories || [])

  const trackingData = data?.items || []
  const totalItems = data?.total || 0
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
        header: 'Instance ID',
        accessorKey: 'instance_id',
        cell: (c) => <span className="font-mono text-xs">{c.getValue() || '-'}</span>,
      },
      {
        header: 'Serial Number',
        accessorKey: 'serial_number',
        cell: (c) => <span className="font-mono text-xs">{c.getValue() || '-'}</span>,
      },
      {
        header: 'Assigned To',
        accessorKey: 'assigned_to',
        cell: (c) => (
          <span className="font-medium text-slate-900">{c.getValue() || '-'}</span>
        ),
      },
      {
        header: 'Employee',
        accessorKey: 'employee_name',
        cell: ({ row }) => row.original.employee_name || row.original.emp_id || '-',
      },
      {
        header: 'Branch',
        accessorKey: 'branch',
        cell: (c) => c.getValue() || '-',
      },
      {
        header: 'Status',
        accessorKey: 'status',
        cell: (c) => {
          const value = c.getValue()
          return value ? <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${statusBadgeClasses(value)}`}>{value}</span> : '-'
        },
      },
      {
        header: 'Assigned',
        accessorKey: 'assigned_date',
        cell: (c) => formatDate(c.getValue()),
      },
    ],
    [],
  )

  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE))

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
        <div className="p-4 border-b border-slate-100 bg-slate-50/50 grid grid-cols-1 md:grid-cols-5 gap-3">
          <input
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Search asset, instance id, serial number, employee..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
          />
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All statuses</option>
            {statusOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={branchId}
            onChange={(e) => {
              setBranchId(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All branches</option>
            {branchOptions.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={employeeId}
            onChange={(e) => {
              setEmployeeId(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All employees</option>
            {employeeOptions.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={categoryId}
            onChange={(e) => {
              setCategoryId(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All categories</option>
            {categoryOptions.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={movementType}
            onChange={(e) => {
              setMovementType(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All movements</option>
            {['ALLOCATION', 'RETURN', 'TRANSFER', 'SERVICE'].map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={transferStatus}
            onChange={(e) => {
              setTransferStatus(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All transfers</option>
            {['PENDING', 'IN_TRANSIT', 'RECEIVED', 'CANCELLED'].map((ts) => (
              <option key={ts} value={ts}>{ts}</option>
            ))}
          </select>
        </div>
        {isLoading ? (
          <div className="p-16 text-center text-slate-400 animate-pulse">Loading tracking...</div>
        ) : isError ? (
          <div className="p-6 text-rose-700 text-sm">{error?.message}</div>
        ) : trackingData.length === 0 ? (
          <div className="p-16 text-center text-slate-500 text-sm">No records in your scope.</div>
        ) : (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.95fr)] xl:items-start">
            <div className="min-w-0 flex flex-col">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm min-w-[980px]">
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
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={totalItems} />
            </div>

            <aside className="border-t xl:border-t-0 xl:border-l border-slate-200 p-6 bg-slate-50/70 min-h-[200px] xl:min-h-0">
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
