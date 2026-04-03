import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import { canManageStockWrites, canManualStockOverride } from '@/lib/roles'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import { RefreshCw } from 'lucide-react'
import AssetDetailPanel from '@/components/AssetDetailPanel'

export default function Stock() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const canWrite = canManageStockWrites(user.role)
  const canOverride = canManualStockOverride(user.role)
  const [selectedAssetId, setSelectedAssetId] = useState(null)

  const { data = [], isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['stock'],
    queryFn: () => apiFetch('/stock/'),
  })

  const selectedStockAsset = useMemo(() => {
    if (!data.length) return null
    return data.find((item) => item.asset_id === selectedAssetId) || data[0]
  }, [data, selectedAssetId])

  const assetDetailQuery = useQuery({
    queryKey: ['asset-detail', selectedStockAsset?.asset_id],
    queryFn: () => apiFetch(`/assets/${selectedStockAsset.asset_id}/detail`),
    enabled: Boolean(selectedStockAsset?.asset_id),
  })

  const invalidateStockRelated = () => {
    qc.invalidateQueries({ queryKey: ['stock'] })
    qc.invalidateQueries({ queryKey: ['tracking'] })
    qc.invalidateQueries({ queryKey: ['my-assets'] })
  }

  const addMut = useMutation({
    mutationFn: (body) => apiFetch('/stock/add', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidateStockRelated,
  })

  const createMut = useMutation({
    mutationFn: (body) => apiFetch('/stock/', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidateStockRelated,
  })

  const allocateMut = useMutation({
    mutationFn: (body) => apiFetch('/stock/allocate_manual_override', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: (payload) => {
      invalidateStockRelated()
      if (payload?.tracking_id) {
        window.alert(`Assigned. Tracking ID: ${payload.tracking_id}`)
      }
    },
  })

  const returnMut = useMutation({
    mutationFn: (body) => apiFetch('/stock/return_manual_override', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: (payload) => {
      invalidateStockRelated()
      if (payload?.recovered_asset) {
        window.alert(`Returned to stock. Asset: ${payload.recovered_asset}`)
      }
    },
  })

  const columns = useMemo(
    () => [
      { header: 'Asset ID', accessorKey: 'asset_id', cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> },
      { header: 'Name', accessorKey: 'name', cell: (c) => <span className="font-semibold text-slate-800">{c.getValue()}</span> },
      { header: 'Total', accessorKey: 'total_quantity' },
      { header: 'Used', accessorKey: 'used' },
      { header: 'Available', accessorKey: 'unused' },
      {
        header: 'Status',
        accessorKey: 'asset_status',
        cell: (c) => (
          <span className="text-xs font-semibold uppercase text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">{String(c.getValue())}</span>
        ),
      },
    ],
    [],
  )

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Inventory</h1>
          <p className="text-sm text-slate-600 mt-1">
            Catalog and quantities. Register and restock require admin or support. Manual assign and return are{' '}
            <strong className="font-semibold text-slate-800">admin only</strong> (bypasses the request workflow).
          </p>
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

      {canWrite ? <StockForms createMut={createMut} addMut={addMut} /> : null}
      {canOverride ? <AdminAllocateReturn allocateMut={allocateMut} returnMut={returnMut} /> : null}

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.95fr] items-start">
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
          {isLoading ? (
            <div className="p-16 text-center text-slate-400 animate-pulse">Loading inventory...</div>
          ) : isError ? (
            <div className="p-6 text-rose-700 text-sm">{error?.message}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm min-w-[720px]">
                <thead>
                  {table.getHeaderGroups().map((hg) => (
                    <tr key={hg.id} className="bg-slate-50 border-b border-slate-200">
                      {hg.headers.map((h) => (
                        <th
                          key={h.id}
                          className="p-4 font-semibold text-slate-600 cursor-pointer text-xs uppercase tracking-wider"
                          onClick={h.column.getToggleSortingHandler()}
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                          {{ asc: ' ↑', desc: ' ↓' }[h.column.getIsSorted()] ?? ''}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {table.getRowModel().rows.map((row) => (
                    <tr key={row.id} className={`cursor-pointer hover:bg-slate-50/80 ${selectedStockAsset?.asset_id === row.original.asset_id ? 'bg-cyan-50/60' : ''}`} onClick={() => setSelectedAssetId(row.original.asset_id)}>
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
        <AssetDetailPanel
          asset={assetDetailQuery.data}
          title="Inventory Asset"
          subtitle={assetDetailQuery.isLoading ? 'Loading selected asset details...' : 'Click any asset row to inspect full details.'}
        />
      </div>
    </div>
  )
}

function StockForms({ createMut, addMut }) {
  const [cid, setCid] = useState('')
  const [cname, setCname] = useState('')
  const [ccat, setCcat] = useState('Hardware')
  const [cbranch, setCbranch] = useState('Headquarters')
  const [cqty, setCqty] = useState('1')
  const [aid, setAid] = useState('')
  const [aqty, setAqty] = useState('1')

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <form
        className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3 shadow-sm"
        onSubmit={(e) => {
          e.preventDefault()
          createMut.mutate({
            asset_id: cid,
            name: cname,
            category_name: ccat,
            sub_category_name: 'General',
            branch: cbranch,
            total_quantity: parseInt(cqty, 10) || 1,
            unused: parseInt(cqty, 10) || 1,
          })
        }}
      >
        <h3 className="font-bold text-slate-900">Register catalog asset</h3>
        <div className="grid grid-cols-2 gap-2">
          <input required className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Asset id" value={cid} onChange={(e) => setCid(e.target.value)} />
          <input required className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Display name" value={cname} onChange={(e) => setCname(e.target.value)} />
          <input className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Category" value={ccat} onChange={(e) => setCcat(e.target.value)} />
          <input className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Branch" value={cbranch} onChange={(e) => setCbranch(e.target.value)} />
          <input className="rounded-lg border border-slate-200 px-3 py-2 text-sm col-span-2" placeholder="Initial quantity" value={cqty} onChange={(e) => setCqty(e.target.value)} />
        </div>
        <button type="submit" disabled={createMut.isPending} className="rounded-xl bg-slate-900 text-white text-sm font-medium px-4 py-2 w-full disabled:opacity-50">
          Create
        </button>
        {createMut.isError ? <p className="text-xs text-rose-600">{createMut.error?.message}</p> : null}
      </form>

      <form
        className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3 shadow-sm"
        onSubmit={(e) => {
          e.preventDefault()
          addMut.mutate({
            asset_id: aid,
            quantity: parseInt(aqty, 10) || 1,
          })
        }}
      >
        <h3 className="font-bold text-slate-900">Add quantity</h3>
        <input required className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Existing asset id" value={aid} onChange={(e) => setAid(e.target.value)} />
        <input required className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Quantity" value={aqty} onChange={(e) => setAqty(e.target.value)} />
        <button type="submit" disabled={addMut.isPending} className="rounded-xl bg-teal-700 text-white text-sm font-medium px-4 py-2 w-full disabled:opacity-50">
          Add stock
        </button>
        {addMut.isError ? <p className="text-xs text-rose-600">{addMut.error?.message}</p> : null}
      </form>
    </div>
  )
}

function AdminAllocateReturn({ allocateMut, returnMut }) {
  const [aAsset, setAAsset] = useState('')
  const [aEmp, setAEmp] = useState('')
  const [aType, setAType] = useState('PERMANENT')
  const [aReason, setAReason] = useState('MANUAL_ALLOCATE')
  const [rTrk, setRTrk] = useState('')
  const [rReason, setRReason] = useState('MANUAL_RETURN')

  return (
    <div className="rounded-2xl border border-amber-200/80 bg-amber-50/40 p-5 space-y-4">
      <h2 className="text-sm font-bold text-amber-900 uppercase tracking-wide">Admin · Manual allocation and return</h2>
      <p className="text-xs text-amber-900/80">
        Uses <code className="bg-white/80 px-1 rounded">allocate_manual_override</code> and <code className="bg-white/80 px-1 rounded">return_manual_override</code>. Tracking IDs appear on <strong>Tracking</strong> and <strong>My assets</strong>. Returning increments available quantity for that catalog asset.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <form
          className="rounded-xl border border-slate-200 bg-white p-4 space-y-3 shadow-sm"
          onSubmit={(e) => {
            e.preventDefault()
            const body = {
              asset_id: aAsset.trim(),
              emp_id: aEmp.trim(),
              allocation_type: aType,
            }
            if (aReason.trim()) body.movement_reason = aReason.trim()
            allocateMut.mutate(body)
          }}
        >
          <h3 className="font-bold text-slate-900 text-sm">Assign unit to employee</h3>
          <input required className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Catalog asset id" value={aAsset} onChange={(e) => setAAsset(e.target.value)} />
          <input required className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Employee id (e.g. EMP-...)" value={aEmp} onChange={(e) => setAEmp(e.target.value)} />
          <select className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" value={aType} onChange={(e) => setAType(e.target.value)}>
            <option value="PERMANENT">Permanent</option>
            <option value="TEMPORARY">Temporary (loaner)</option>
          </select>
          <input className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Movement reason" value={aReason} onChange={(e) => setAReason(e.target.value)} />
          <button type="submit" disabled={allocateMut.isPending} className="w-full rounded-xl bg-amber-700 text-white text-sm font-semibold py-2.5 disabled:opacity-50">
            Allocate
          </button>
          {allocateMut.isError ? <p className="text-xs text-rose-600">{allocateMut.error?.message}</p> : null}
        </form>

        <form
          className="rounded-xl border border-slate-200 bg-white p-4 space-y-3 shadow-sm"
          onSubmit={(e) => {
            e.preventDefault()
            const body = { tracking_id: rTrk.trim() }
            if (rReason.trim()) body.movement_reason = rReason.trim()
            returnMut.mutate(body)
          }}
        >
          <h3 className="font-bold text-slate-900 text-sm">Return assignment to stock</h3>
          <input required className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono text-xs" placeholder="Tracking id (TRK-...)" value={rTrk} onChange={(e) => setRTrk(e.target.value)} />
          <input className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Reason" value={rReason} onChange={(e) => setRReason(e.target.value)} />
          <button type="submit" disabled={returnMut.isPending} className="w-full rounded-xl border-2 border-amber-700 text-amber-900 text-sm font-semibold py-2.5 disabled:opacity-50 bg-white">
            Return / recover
          </button>
          {returnMut.isError ? <p className="text-xs text-rose-600">{returnMut.error?.message}</p> : null}
        </form>
      </div>
    </div>
  )
}
