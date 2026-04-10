import React, { useMemo, useState } from 'react'
import Pagination from '@/components/Pagination'
import ConfirmDialog from '@/components/ConfirmDialog'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import { normalizeOptions } from '@/lib/options'
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
  const canDeleteAsset = user.role === 'super_admin' || user.role === 'org_admin'
  const [selectedAssetId, setSelectedAssetId] = useState(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15
  const [searchInput, setSearchInput] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [subCategoryFilter, setSubCategoryFilter] = useState('')
  const [branchFilter, setBranchFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [instancePage, setInstancePage] = useState(1)
  const [instanceSearch, setInstanceSearch] = useState('')
  const [instanceCategoryId, setInstanceCategoryId] = useState('')
  const [instanceBranchId, setInstanceBranchId] = useState('')
  const [instanceStatus, setInstanceStatus] = useState('')
  const [instanceAssignedToId, setInstanceAssignedToId] = useState('')

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['assets', page, searchInput, categoryFilter, subCategoryFilter, branchFilter, statusFilter],
    queryFn: () => {
      const params = new URLSearchParams({
        page: page.toString(),
        per_page: PAGE_SIZE.toString(),
      })
      if (searchInput.trim()) params.set('search', searchInput.trim())
      if (categoryFilter) params.set('category_id', categoryFilter)
      if (subCategoryFilter) params.set('sub_category_id', subCategoryFilter)
      if (branchFilter) params.set('branch_id', branchFilter)
      if (statusFilter) params.set('status', statusFilter)
      return apiFetch(`/assets/?${params.toString()}`)
    },
  })

  const { data: modelOptions = [] } = useQuery({
    queryKey: ['asset-model-options'],
    queryFn: () => apiFetch('/assets/options'),
  })

  const { data: stockCategoriesRaw = [] } = useQuery({
    queryKey: ['stock-categories-list'],
    queryFn: () => apiFetch('/stock/categories'),
  })

  const { data: tenantBranchesRaw = [] } = useQuery({
    queryKey: ['tenant-branches-list'],
    queryFn: () => apiFetch('/stock/branches-list'),
  })

  const { data: statusOptionsRaw = [] } = useQuery({
    queryKey: ['asset-statuses-list'],
    queryFn: () => apiFetch('/stock/statuses'),
  })

  const categoryOptions = useMemo(() => normalizeOptions(stockCategoriesRaw), [stockCategoriesRaw])
  const branchOptions = useMemo(() => normalizeOptions(tenantBranchesRaw), [tenantBranchesRaw])
  const statusOptions = useMemo(() => statusOptionsRaw, [statusOptionsRaw])

  const { data: subCategoriesFilterRaw = [] } = useQuery({
    queryKey: ['stock-sub-categories-filter', categoryFilter],
    queryFn: () => apiFetch(`/stock/sub-categories?category_id=${categoryFilter}`),
    enabled: Boolean(categoryFilter),
  })

  const subCategoryOptions = useMemo(() => normalizeOptions(subCategoriesFilterRaw), [subCategoriesFilterRaw])

  const { data: instanceOptions } = useQuery({
    queryKey: ['asset-instance-options'],
    queryFn: () => apiFetch('/asset-instances/options'),
  })

  const { data: instanceData, isLoading: instanceLoading, isError: instanceError, error: instanceErrorObj } = useQuery({
    queryKey: ['asset-instances', instancePage, instanceSearch, instanceCategoryId, instanceBranchId, instanceStatus, instanceAssignedToId],
    queryFn: () => {
      const params = new URLSearchParams({
        page: instancePage.toString(),
        per_page: PAGE_SIZE.toString(),
      })
      if (instanceSearch.trim()) params.set('search', instanceSearch.trim())
      if (instanceCategoryId) params.set('category_id', instanceCategoryId)
      if (instanceBranchId) params.set('branch_id', instanceBranchId)
      if (instanceStatus) params.set('status', instanceStatus)
      if (instanceAssignedToId) params.set('assigned_to_id', instanceAssignedToId)
      return apiFetch(`/asset-instances?${params.toString()}`)
    },
  })

  const totalItems = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE))
  const items = data?.items || []
  const instanceItems = instanceData?.items || []
  const instanceTotal = instanceData?.total || 0
  const instanceTotalPages = Math.max(1, Math.ceil(instanceTotal / PAGE_SIZE))
  const instanceStatusOptions = statusOptions
  const instanceBranchOptions = branchOptions
  const instanceCategoryOptions = categoryOptions
  const instanceAssigneeOptions = normalizeOptions(instanceOptions?.assignees || [])



  const selectedStockAsset = useMemo(() => {
    return items.find((item) => item.asset_id === selectedAssetId) || null
  }, [items, selectedAssetId])

  const assetDetailQuery = useQuery({
    queryKey: ['asset-detail', selectedStockAsset?.asset_id],
    queryFn: () => apiFetch(`/assets/${selectedStockAsset.asset_id}/detail`),
    enabled: Boolean(selectedStockAsset?.asset_id),
  })

  const selectedAssetInstancesQuery = useQuery({
    queryKey: ['asset-detail-instances', selectedStockAsset?.asset_id],
    queryFn: () => apiFetch(`/stock/instances?asset_id=${selectedStockAsset.asset_id}&page=1&per_page=200`),
    enabled: Boolean(selectedStockAsset?.asset_id),
  })

  const invalidateStockRelated = () => {
    qc.invalidateQueries({ queryKey: ['assets'] })
    qc.invalidateQueries({ queryKey: ['asset-model-options'] })
    qc.invalidateQueries({ queryKey: ['tracking'] })
    qc.invalidateQueries({ queryKey: ['my-assets'] })
  }

  const createMut = useMutation({
    mutationFn: (body) => apiFetch('/stock/', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: invalidateStockRelated,
  })

  const deleteMut = useMutation({
    mutationFn: (assetId) => apiFetch(`/stock/${assetId}`, { method: 'DELETE' }),
    onSuccess: (_, assetId) => {
      if (selectedAssetId === assetId) {
        setDetailsOpen(false)
        setSelectedAssetId(null)
      }
      setDeleteTarget(null)
      invalidateStockRelated()
    },
  })

  const columns = useMemo(
    () => [
      { header: 'Asset ID', accessorKey: 'asset_id', cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> },
      { header: 'Name', accessorKey: 'name', cell: (c) => <span className="font-semibold text-slate-800">{c.getValue()}</span> },
      { header: 'Brand', accessorKey: 'brand', cell: (c) => c.getValue() || '—' },
      { header: 'Total', accessorKey: 'total_quantity' },
      { header: 'Used', accessorKey: 'used' },
      { header: 'Available', accessorKey: 'unused' },
      {
        header: 'Status',
        accessorKey: 'status',
        cell: (c) => (
          <span className="text-xs font-semibold uppercase text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">{String(c.getValue())}</span>
        ),
      },
      {
        header: 'Actions',
        id: 'actions',
        cell: ({ row }) => (
          canDeleteAsset ? (
            <button
              type="button"
              className="rounded-lg border border-rose-200 bg-rose-50 px-2 py-1 text-xs font-medium text-rose-700 hover:bg-rose-100"
              onClick={(event) => {
                event.stopPropagation()
                setDeleteTarget({ asset_id: row.original.asset_id, name: row.original.name })
              }}
            >
              Remove
            </button>
          ) : (
            <span className="text-xs text-slate-400">—</span>
          )
        ),
      },
    ],
    [canDeleteAsset],
  )

  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Asset Models</h1>
          <p className="text-sm text-slate-600 mt-1">
            Asset models and physical instances. Registering catalog assets requires admin or support.
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

      {canWrite ? <StockForms createMut={createMut} categories={categoryOptions} branches={branchOptions} /> : null}

      <div className="grid gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="p-4 border-b border-slate-100 bg-slate-50/50 space-y-3">
            <div className="flex flex-col md:flex-row items-center gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  className="w-full rounded-xl border border-slate-200 pl-10 pr-3 py-2 text-sm bg-white"
                  placeholder="Search asset name, brand, model, category, sub-category, branch, or status..."
                  value={searchInput}
                  onChange={(e) => { setSearchInput(e.target.value); setPage(1) }}
                  autoComplete="off"
                />
              </div>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={categoryFilter} onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}>
                <option value="">All Categories</option>
                {categoryOptions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={subCategoryFilter} onChange={(e) => { setSubCategoryFilter(e.target.value); setPage(1) }} disabled={!categoryFilter}>
                <option value="">All Sub-categories</option>
                {subCategoryOptions.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={branchFilter} onChange={(e) => { setBranchFilter(e.target.value); setPage(1) }}>
                <option value="">All Branches</option>
                {branchOptions.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>

              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}>
                <option value="">All Statuses</option>
                {statusOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              {searchInput || categoryFilter || subCategoryFilter || branchFilter || statusFilter ? (
                <button
                  type="button"
                  className="text-xs text-slate-500 hover:text-slate-700 font-medium"
                  onClick={() => { setSearchInput(''); setCategoryFilter(''); setSubCategoryFilter(''); setBranchFilter(''); setStatusFilter(''); setPage(1) }}
                >
                  Reset
                </button>
              ) : null}
            </div>
          </div>

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
                    <tr key={row.id} className={`cursor-pointer hover:bg-slate-50/80 ${selectedStockAsset?.asset_id === row.original.asset_id ? 'bg-cyan-50/60' : ''}`} onClick={() => { setSelectedAssetId(row.original.asset_id); setDetailsOpen(true) }}>
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="p-4 text-slate-700">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {items.length === 0 && (
                    <tr>
                      <td colSpan={columns.length} className="p-16 text-center text-slate-400">No assets found</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={totalItems} />
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="p-4 border-b border-slate-100 bg-slate-50/50 space-y-3">
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-[0.16em]">Asset Instances</h2>
            <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
              <input
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white md:col-span-2"
                placeholder="Search instance id, asset name, or assigned employee..."
                value={instanceSearch}
                onChange={(e) => { setInstanceSearch(e.target.value); setInstancePage(1) }}
              />
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={instanceCategoryId} onChange={(e) => { setInstanceCategoryId(e.target.value); setInstancePage(1) }}>
                <option value="">All Categories</option>
                {instanceCategoryOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={instanceBranchId} onChange={(e) => { setInstanceBranchId(e.target.value); setInstancePage(1) }}>
                <option value="">All Branches</option>
                {instanceBranchOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={instanceStatus} onChange={(e) => { setInstanceStatus(e.target.value); setInstancePage(1) }}>
                <option value="">All Statuses</option>
                {instanceStatusOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={instanceAssignedToId} onChange={(e) => { setInstanceAssignedToId(e.target.value); setInstancePage(1) }}>
                <option value="">All Assignees</option>
                {instanceAssigneeOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </div>
          </div>

          {instanceLoading ? (
            <div className="p-16 text-center text-slate-400 animate-pulse">Loading asset instances...</div>
          ) : instanceError ? (
            <div className="p-6 text-rose-700 text-sm">{instanceErrorObj?.message}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm min-w-[1100px]">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Instance ID</th>
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Asset Name</th>
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Brand</th>
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Branch</th>
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Status</th>
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Assigned To</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {instanceItems.map((row) => (
                    <tr key={row.instance_id} className="hover:bg-slate-50/80">
                      <td className="p-4 font-mono text-xs text-slate-700">{row.instance_id}</td>
                      <td className="p-4 text-slate-700">{row.asset_name || '—'}</td>
                      <td className="p-4 text-slate-700">{row.brand || '—'}</td>
                      <td className="p-4 text-slate-700">{row.branch || '—'}</td>
                      <td className="p-4">
                        <span className="text-xs font-semibold uppercase text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">{row.status || '—'}</span>
                      </td>
                      <td className="p-4 text-slate-700">{row.assigned_to || row.assigned_to_id || '—'}</td>
                    </tr>
                  ))}
                  {instanceItems.length === 0 && (
                    <tr>
                      <td colSpan={6} className="p-16 text-center text-slate-400">No asset instances found</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
          <Pagination page={instancePage} totalPages={instanceTotalPages} onPageChange={setInstancePage} pageSize={PAGE_SIZE} total={instanceTotal} />
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
                  instances={selectedAssetInstancesQuery.data?.items || []}
                  title="Inventory Asset"
                  subtitle={assetDetailQuery.isLoading ? 'Loading selected asset details...' : 'Selected asset details.'}
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget ? `Remove asset ${deleteTarget.name}?` : ''}
        description="This deletes the asset model only if it has no assignments, tracking history, or linked requests."
        confirmLabel="Remove asset"
        busy={deleteMut.isPending}
        onCancel={() => { if (!deleteMut.isPending) setDeleteTarget(null) }}
        onConfirm={() => {
          if (!deleteTarget || deleteMut.isPending) return
          deleteMut.mutate(deleteTarget.asset_id)
        }}
      />
    </div>
  )
}

function StockForms({ createMut, categories, branches }) {
  const NEW_OPTION_VALUE = '__new__'
  const PRESET_PREFIX = '__preset__:'
  const today = useMemo(() => new Date().toISOString().slice(0, 10), [])

  const newSpecRow = () => ({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    attributeRef: '',
    newAttributeName: '',
    value: '',
  })

  const [assetName, setAssetName] = useState('')
  const [ccat, setCcat] = useState('')
  const [cnewCategoryName, setCnewCategoryName] = useState('')
  const [csub, setCsub] = useState('')
  const [cnewSubCategoryName, setCnewSubCategoryName] = useState('')
  const [cbranchId, setCbranchId] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [purchaseDate, setPurchaseDate] = useState(today)
  const [purchaseCost, setPurchaseCost] = useState('')
  const [vendorName, setVendorName] = useState('')
  const [vendorContact, setVendorContact] = useState('')
  const [invoiceNumber, setInvoiceNumber] = useState('')
  const [expiryDate, setExpiryDate] = useState('')
  const [usefulLifeYears, setUsefulLifeYears] = useState('5')
  const [specRows, setSpecRows] = useState([newSpecRow()])

  const selectedCategory = categories.find((item) => item.id === ccat)
  const selectedCategoryName = (selectedCategory?.name || '').toLowerCase()
  const commonSpecs = useMemo(() => {
    if (!ccat) return []
    if (selectedCategoryName.includes('software') || selectedCategoryName.includes('license')) {
      return ['Vendor', 'Version', 'License Key']
    }
    if (selectedCategoryName.includes('hardware') || selectedCategoryName.includes('laptop') || selectedCategoryName.includes('desktop') || selectedCategoryName.includes('server')) {
      return ['Brand', 'Model', 'RAM', 'CPU', 'Storage', 'Serial Number']
    }
    return ['Brand', 'Model', 'Serial Number']
  }, [ccat, selectedCategoryName])

  const { data: subCategories = [] } = useQuery({
    queryKey: ['stock-sub-categories', ccat],
    queryFn: () => apiFetch(`/stock/sub-categories?category_id=${ccat}`),
    enabled: Boolean(ccat) && ccat !== NEW_OPTION_VALUE,
  })

  const { data: attributeOptions = [] } = useQuery({
    queryKey: ['stock-attribute-options', csub],
    queryFn: () => apiFetch(`/stock/attributes/options?sub_category_id=${csub}`),
    enabled: Boolean(csub) && csub !== NEW_OPTION_VALUE,
  })

  const updateSpecRow = (rowId, patch) => {
    setSpecRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, ...patch } : row)))
  }

  const addSpecRow = () => setSpecRows((prev) => [...prev, newSpecRow()])

  const removeSpecRow = (rowId) => {
    setSpecRows((prev) => (prev.length <= 1 ? [newSpecRow()] : prev.filter((row) => row.id !== rowId)))
  }

  const resetForm = () => {
    setAssetName('')
    setCcat('')
    setCnewCategoryName('')
    setCsub('')
    setCnewSubCategoryName('')
    setCbranchId('')
    setQuantity('1')
    setPurchaseDate(today)
    setPurchaseCost('')
    setVendorName('')
    setVendorContact('')
    setInvoiceNumber('')
    setExpiryDate('')
    setUsefulLifeYears('5')
    setSpecRows([newSpecRow()])
  }

  return (
    <div className="grid grid-cols-1 gap-4">
      <form
        className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4 shadow-sm"
        onSubmit={(e) => {
          e.preventDefault()

          const isNewCategory = ccat === NEW_OPTION_VALUE
          const isNewSubCategory = csub === NEW_OPTION_VALUE
          const categoryName = cnewCategoryName.trim()
          const subCategoryName = cnewSubCategoryName.trim()

          if (!assetName.trim()) return
          if (!quantity || Number(quantity) <= 0) return
          if (isNewCategory && !categoryName) return
          if (isNewSubCategory && !subCategoryName) return

          const specifications = specRows
            .map((row) => {
              const value = row.value.trim()
              if (!value) return null

              if (row.attributeRef.startsWith(PRESET_PREFIX)) {
                const attributeName = row.attributeRef.slice(PRESET_PREFIX.length).trim()
                if (!attributeName) return null
                return { attribute_name: attributeName, value }
              }

              if (row.attributeRef === NEW_OPTION_VALUE) {
                const attributeName = row.newAttributeName.trim()
                if (!attributeName) return null
                return { attribute_name: attributeName, value }
              }

              if (row.attributeRef) {
                return { attribute_id: row.attributeRef, value }
              }

              return null
            })
            .filter(Boolean)

          createMut.mutate(
            {
              name: assetName.trim(),
              category_id: isNewCategory ? null : ccat || null,
              category_name: isNewCategory ? categoryName : null,
              sub_category_id: isNewSubCategory || isNewCategory ? null : csub || null,
              sub_category_name: isNewSubCategory ? subCategoryName : isNewCategory && subCategoryName ? subCategoryName : null,
              branch_id: cbranchId || null,
              purchased_date: purchaseDate || null,
              purchase_cost: purchaseCost ? Number(purchaseCost) : null,
              vendor_name: vendorName.trim() || null,
              vendor_contact: vendorContact.trim() || null,
              invoice_number: invoiceNumber.trim() || null,
              expiry_date: expiryDate || null,
              useful_life_years: Number(usefulLifeYears) || 5,
              total_quantity: Number(quantity) || 1,
              unused: Number(quantity) || 1,
              specifications,
            },
            {
              onSuccess: () => resetForm(),
            },
          )
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-bold text-slate-900">Register catalog asset</h3>
            <p className="text-xs text-slate-500 mt-1">Organization is resolved from your session. Brand, model, and other specs are captured as dynamic attributes.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="md:col-span-2 text-xs font-medium text-slate-600">
            Asset name
            <input required className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Asset name" value={assetName} onChange={(e) => setAssetName(e.target.value)} />
          </label>
          <select
            required
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            value={ccat}
            onChange={(e) => {
              setCcat(e.target.value)
              setCsub('')
              setCnewSubCategoryName('')
            }}
          >
            <option value="">Select category</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
            <option value={NEW_OPTION_VALUE}>Add new category</option>
          </select>

          {ccat === NEW_OPTION_VALUE ? (
            <label className="text-xs font-medium text-slate-600">
              New category name
              <input
                required
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                placeholder="New category name"
                value={cnewCategoryName}
                onChange={(e) => setCnewCategoryName(e.target.value)}
              />
            </label>
          ) : (
            <select
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              value={csub}
              onChange={(e) => setCsub(e.target.value)}
              disabled={!ccat}
            >
              <option value="">Select sub-category</option>
              {subCategories.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
              <option value={NEW_OPTION_VALUE}>Add new sub-category</option>
            </select>
          )}

          {ccat === NEW_OPTION_VALUE || csub === NEW_OPTION_VALUE ? (
            <label className="md:col-span-2 text-xs font-medium text-slate-600">
              New sub-category name
              <input
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                placeholder="New sub-category name"
                value={cnewSubCategoryName}
                onChange={(e) => setCnewSubCategoryName(e.target.value)}
              />
            </label>
          ) : null}

          <label className="text-xs font-medium text-slate-600">
            Branch
            <select className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" value={cbranchId} onChange={(e) => setCbranchId(e.target.value)}>
              <option value="">Branch (optional)</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>

          <label className="text-xs font-medium text-slate-600">
            Quantity
            <input required type="number" min="1" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Quantity" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Purchase date
            <input type="date" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Purchase cost
            <input type="number" step="0.01" min="0" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Purchase cost" value={purchaseCost} onChange={(e) => setPurchaseCost(e.target.value)} />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Vendor name
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Vendor name" value={vendorName} onChange={(e) => setVendorName(e.target.value)} />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Vendor contact
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Vendor contact" value={vendorContact} onChange={(e) => setVendorContact(e.target.value)} />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Invoice number
            <input className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Invoice number" value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Expiry date
            <input type="date" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
          </label>
          <label className="md:col-span-2 text-xs font-medium text-slate-600">
            Useful life in years
            <input type="number" min="1" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Useful life in years" value={usefulLifeYears} onChange={(e) => setUsefulLifeYears(e.target.value)} />
          </label>
        </div>

        <div className="rounded-xl border border-slate-200 p-3 space-y-3 bg-slate-50/50">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-slate-800">Specifications</h4>
              <p className="text-xs text-slate-500">Use dynamic attributes for the selected category. Expiry is captured directly in the form now.</p>
            </div>
            <button type="button" className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700" onClick={addSpecRow}>
              Add spec row
            </button>
          </div>

          {specRows.map((row) => (
            <div key={row.id} className="grid grid-cols-1 md:grid-cols-12 gap-2 items-start">
              <label className="text-xs font-medium text-slate-600 md:col-span-5">
                Attribute
                <select
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white"
                  value={row.attributeRef}
                  onChange={(e) => updateSpecRow(row.id, { attributeRef: e.target.value, newAttributeName: e.target.value === NEW_OPTION_VALUE ? row.newAttributeName : '' })}
                  disabled={!ccat}
                >
                  <option value="">Select attribute</option>
                  {commonSpecs.map((name) => (
                    <option key={name} value={`${PRESET_PREFIX}${name}`}>
                      {name}
                    </option>
                  ))}
                  {attributeOptions.map((item) => (
                    <option key={item.attribute_id} value={item.attribute_id}>
                      {item.attribute_name}
                    </option>
                  ))}
                  <option value={NEW_OPTION_VALUE}>Add new attribute</option>
                </select>
              </label>

              {row.attributeRef === NEW_OPTION_VALUE ? (
                <label className="text-xs font-medium text-slate-600 md:col-span-3">
                  New attribute name
                  <input
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    placeholder="New attribute name"
                    value={row.newAttributeName}
                    onChange={(e) => updateSpecRow(row.id, { newAttributeName: e.target.value })}
                  />
                </label>
              ) : (
                <div className="md:col-span-3" />
              )}

              <label className="text-xs font-medium text-slate-600 md:col-span-3">
                Value
                <input
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  placeholder="Value"
                  value={row.value}
                  onChange={(e) => updateSpecRow(row.id, { value: e.target.value })}
                />
              </label>

              <button type="button" className="rounded-lg border border-rose-200 px-2 py-2 text-xs font-medium text-rose-700 md:col-span-1 bg-white" onClick={() => removeSpecRow(row.id)} aria-label="Remove specification row">
                Remove
              </button>
            </div>
          ))}

          {!ccat ? (
            <p className="text-xs text-amber-700">Select a category first. Fields and attribute presets change with the selected category.</p>
          ) : csub === NEW_OPTION_VALUE ? (
            <p className="text-xs text-slate-600">New sub-category selected. Use preset attributes or add custom attributes.</p>
          ) : !csub ? (
            <p className="text-xs text-amber-700">Select a sub-category to load existing attribute options.</p>
          ) : null}
        </div>

        <button type="submit" disabled={createMut.isPending} className="rounded-xl bg-slate-900 text-white text-sm font-medium px-4 py-2 w-full disabled:opacity-50">
          Create asset
        </button>
        {createMut.isError ? <p className="text-xs text-rose-600">{createMut.error?.message}</p> : null}
      </form>
    </div>
  )
}

