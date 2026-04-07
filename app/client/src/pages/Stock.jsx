import React, { useEffect, useMemo, useState } from 'react'
import Pagination from '@/components/Pagination'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import { canManageStockWrites } from '@/lib/roles'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import { RefreshCw } from 'lucide-react'
import AssetDetailPanel from '@/components/AssetDetailPanel'
import { Search } from 'lucide-react'

export default function Stock() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const canWrite = canManageStockWrites(user.role)
  const [selectedAssetId, setSelectedAssetId] = useState(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15
  const [searchInput, setSearchInput] = useState('')

  const { data = [], isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['stock'],
    queryFn: () => apiFetch('/stock/'),
  })

  const selectedStockAsset = useMemo(() => {
    return data.find((item) => item.asset_id === selectedAssetId) || null
  }, [data, selectedAssetId])

  const filteredData = useMemo(() => {
    const t = searchInput.trim().toLowerCase()
    if (!t) return data
    return data.filter((a) => {
      const assetId = String(a.asset_id || '').toLowerCase()
      const name = String(a.name || '').toLowerCase()
      return assetId.includes(t) || name.includes(t)
    })
  }, [data, searchInput])

  useEffect(() => {
    setPage(1)
  }, [searchInput])

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

  const totalPages = Math.max(1, Math.ceil(filteredData.length / PAGE_SIZE))
  const pagedData = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return filteredData.slice(start, start + PAGE_SIZE)
  }, [filteredData, page, PAGE_SIZE])

  const table = useReactTable({
    data: pagedData,
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
            Catalog and quantities. Register and restock require admin or support.
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

      <div className="grid gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
          {isLoading ? (
            <div className="p-16 text-center text-slate-400 animate-pulse">Loading inventory...</div>
          ) : isError ? (
            <div className="p-6 text-rose-700 text-sm">{error?.message}</div>
          ) : (
            <div className="overflow-x-auto">
              <div className="p-4 border-b border-slate-100 bg-slate-50/50">
                <div className="flex items-center gap-2">
                  <Search className="w-4 h-4 text-slate-400" />
                  <input
                    className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white"
                    placeholder="Search inventory by asset id or name"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    autoComplete="off"
                  />
                  {searchInput ? (
                    <button
                      type="button"
                      className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-600 bg-white"
                      onClick={() => setSearchInput('')}
                    >
                      Clear
                    </button>
                  ) : null}
                </div>
              </div>

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
                    <tr key={row.id} className={`cursor-pointer hover:bg-slate-50/80 ${selectedStockAsset?.asset_id === row.original.asset_id ? 'bg-cyan-50/60' : ''}`} onClick={() => { setSelectedAssetId(row.original.asset_id); setDetailsOpen(true) }}>
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
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={filteredData.length} />
        </div>
      </div>

      {detailsOpen && selectedStockAsset ? (
        <div className="fixed inset-0 z-[9999] overflow-y-auto bg-slate-900/70 backdrop-blur-sm" onClick={() => { setDetailsOpen(false); setSelectedAssetId(null) }}>
          <div className="mx-auto mt-10 mb-10 w-full max-w-6xl overflow-auto rounded-3xl bg-white shadow-2xl border border-slate-200" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className="absolute right-4 top-4 inline-flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200"
              onClick={() => setDetailsOpen(false)}
              aria-label="Close asset details"
            >
              ×
            </button>
            <div className="p-6">
              <div className="space-y-6">
                <AssetDetailPanel
                  asset={assetDetailQuery.data}
                  title="Inventory Asset"
                  subtitle={assetDetailQuery.isLoading ? 'Loading selected asset details...' : 'Selected asset details.'}
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function StockForms({ createMut, addMut }) {
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

