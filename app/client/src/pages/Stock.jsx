import React, { useMemo, useState } from 'react'
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
      return apiFetch(`/assets?${params.toString()}`)
    },
  })

  const { data: modelOptions = [] } = useQuery({
    queryKey: ['asset-model-options'],
    queryFn: () => apiFetch('/assets/options'),
  })

  const categoryOptions = useMemo(() => {
    const seen = new Map()
    for (const item of modelOptions) {
      if (item.category_id && item.category && !seen.has(item.category_id)) {
        seen.set(item.category_id, item.category)
      }
    }
    return [...seen.entries()]
      .map(([id, name]) => ({ category_id: id, category_name: name }))
      .sort((a, b) => String(a.category_name).localeCompare(String(b.category_name)))
  }, [modelOptions])

  const subCategoryOptions = useMemo(() => {
    const seen = new Map()
    for (const item of modelOptions) {
      if (categoryFilter && item.category_id !== categoryFilter) continue
      if (item.sub_category_id && item.sub_category && !seen.has(item.sub_category_id)) {
        seen.set(item.sub_category_id, item.sub_category)
      }
    }
    return [...seen.entries()]
      .map(([id, name]) => ({ sub_category_id: id, sub_category_name: name }))
      .sort((a, b) => String(a.sub_category_name).localeCompare(String(b.sub_category_name)))
  }, [modelOptions, categoryFilter])

  const branchOptions = useMemo(() => {
    const seen = new Map()
    for (const item of modelOptions) {
      if (item.branch_id && item.branch && !seen.has(item.branch_id)) {
        seen.set(item.branch_id, item.branch)
      }
    }
    return [...seen.entries()]
      .map(([id, name]) => ({ branch_id: id, branch_name: name }))
      .sort((a, b) => String(a.branch_name).localeCompare(String(b.branch_name)))
  }, [modelOptions])

  const statusOptions = useMemo(() => {
    const setValues = new Set(modelOptions.map((item) => item.status).filter(Boolean))
    return [...setValues].sort((a, b) => String(a).localeCompare(String(b)))
  }, [modelOptions])

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
  const instanceStatusOptions = instanceOptions?.statuses || []
  const instanceBranchOptions = instanceOptions?.branches || []
  const instanceCategoryOptions = instanceOptions?.categories || []
  const instanceAssigneeOptions = instanceOptions?.assignees || []

  const selectedStockAsset = useMemo(() => {
    return items.find((item) => item.asset_id === selectedAssetId) || null
  }, [items, selectedAssetId])

  const assetDetailQuery = useQuery({
    queryKey: ['asset-detail', selectedStockAsset?.asset_id],
    queryFn: () => apiFetch(`/assets/${selectedStockAsset.asset_id}/detail`),
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

  const columns = useMemo(
    () => [
      { header: 'Asset ID', accessorKey: 'asset_id', cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span> },
      { header: 'Name', accessorKey: 'name', cell: (c) => <span className="font-semibold text-slate-800">{c.getValue()}</span> },
      { header: 'Brand', accessorKey: 'brand', cell: (c) => c.getValue() || '—' },
      { header: 'Model', accessorKey: 'model', cell: (c) => c.getValue() || '—' },
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
    ],
    [],
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
                {categoryOptions.map(c => <option key={c.category_id} value={c.category_id}>{c.category_name}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={subCategoryFilter} onChange={(e) => { setSubCategoryFilter(e.target.value); setPage(1) }} disabled={!categoryFilter}>
                <option value="">All Sub-categories</option>
                {subCategoryOptions.map(s => <option key={s.sub_category_id} value={s.sub_category_id}>{s.sub_category_name}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={branchFilter} onChange={(e) => { setBranchFilter(e.target.value); setPage(1) }}>
                <option value="">All Branches</option>
                {branchOptions.map(b => <option key={b.branch_id} value={b.branch_id}>{b.branch_name}</option>)}
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
                placeholder="Search instance id, serial number, asset name, or assigned employee..."
                value={instanceSearch}
                onChange={(e) => { setInstanceSearch(e.target.value); setInstancePage(1) }}
              />
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={instanceCategoryId} onChange={(e) => { setInstanceCategoryId(e.target.value); setInstancePage(1) }}>
                <option value="">All Categories</option>
                {instanceCategoryOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={instanceBranchId} onChange={(e) => { setInstanceBranchId(e.target.value); setInstancePage(1) }}>
                <option value="">All Branches</option>
                {instanceBranchOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={instanceStatus} onChange={(e) => { setInstanceStatus(e.target.value); setInstancePage(1) }}>
                <option value="">All Statuses</option>
                {instanceStatusOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm bg-white" value={instanceAssignedToId} onChange={(e) => { setInstanceAssignedToId(e.target.value); setInstancePage(1) }}>
                <option value="">All Assignees</option>
                {instanceAssigneeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
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
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Model</th>
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Branch</th>
                    <th className="p-4 font-semibold text-slate-600 text-xs uppercase tracking-wider">Serial Number</th>
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
                      <td className="p-4 text-slate-700">{row.model || '—'}</td>
                      <td className="p-4 text-slate-700">{row.branch || '—'}</td>
                      <td className="p-4 text-slate-700">{row.serial_number || '—'}</td>
                      <td className="p-4">
                        <span className="text-xs font-semibold uppercase text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md">{row.status || '—'}</span>
                      </td>
                      <td className="p-4 text-slate-700">{row.assigned_to || row.assigned_to_id || '—'}</td>
                    </tr>
                  ))}
                  {instanceItems.length === 0 && (
                    <tr>
                      <td colSpan={8} className="p-16 text-center text-slate-400">No asset instances found</td>
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

function StockForms({ createMut, categories, branches }) {
  const NEW_OPTION_VALUE = '__new__'

  const newSpecRow = () => ({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    attributeRef: '',
    newAttributeName: '',
    value: '',
  })

  const [cname, setCname] = useState('')
  const [cbrand, setCbrand] = useState('')
  const [cmodel, setCmodel] = useState('')
  const [ccat, setCcat] = useState('')
  const [cnewCategoryName, setCnewCategoryName] = useState('')
  const [csub, setCsub] = useState('')
  const [cnewSubCategoryName, setCnewSubCategoryName] = useState('')
  const [cbranchId, setCbranchId] = useState('')
  const [cqty, setCqty] = useState('1')
  const [specRows, setSpecRows] = useState([newSpecRow()])

  const { data: subCategories = [] } = useQuery({
    queryKey: ['stock-sub-categories', ccat],
    queryFn: () => apiFetch(`/stock/sub-categories?category_id=${ccat}`),
    enabled: Boolean(ccat) && ccat !== NEW_OPTION_VALUE,
  })

  const { data: attributeOptions = [] } = useQuery({
    queryKey: ['stock-attribute-options', csub],
    queryFn: () => apiFetch(`/stock/attributes/options?sub_category_id=${csub}`),
    enabled: Boolean(csub),
  })

  const updateSpecRow = (rowId, patch) => {
    setSpecRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, ...patch } : row)))
  }

  const addSpecRow = () => {
    setSpecRows((prev) => [...prev, newSpecRow()])
  }

  const removeSpecRow = (rowId) => {
    setSpecRows((prev) => {
      if (prev.length <= 1) {
        return [newSpecRow()]
      }
      return prev.filter((row) => row.id !== rowId)
    })
  }

  const resetForm = () => {
    setCname('')
    setCbrand('')
    setCmodel('')
    setCcat('')
    setCnewCategoryName('')
    setCsub('')
    setCnewSubCategoryName('')
    setCbranchId('')
    setCqty('1')
    setSpecRows([newSpecRow()])
  }

  return (
    <div className="grid grid-cols-1 gap-4">
      <form
        className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3 shadow-sm"
        onSubmit={(e) => {
          e.preventDefault()

          const isNewCategory = ccat === NEW_OPTION_VALUE
          const isNewSubCategory = csub === NEW_OPTION_VALUE
          const categoryName = cnewCategoryName.trim()
          const subCategoryName = cnewSubCategoryName.trim()

          if (isNewCategory && !categoryName) {
            return
          }

          if (isNewSubCategory && !subCategoryName) {
            return
          }

          const specifications = specRows
            .map((row) => {
              const value = row.value.trim()
              if (!value) return null

              if (row.attributeRef === '__new__') {
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

          createMut.mutate({
            name: cname,
            brand: cbrand,
            model: cmodel,
            category_id: isNewCategory ? null : ccat,
            category_name: isNewCategory ? categoryName : null,
            sub_category_id: isNewSubCategory || isNewCategory ? null : csub || null,
            sub_category_name: isNewSubCategory ? subCategoryName : (isNewCategory && subCategoryName ? subCategoryName : null),
            branch_id: cbranchId || null,
            total_quantity: parseInt(cqty, 10) || 1,
            unused: parseInt(cqty, 10) || 1,
            specifications,
          }, {
            onSuccess: () => {
              resetForm()
            },
          })
        }}
      >
        <h3 className="font-bold text-slate-900">Register catalog asset</h3>
        <div className="grid grid-cols-2 gap-2">
          <input required className="rounded-lg border border-slate-200 px-3 py-2 text-sm col-span-2" placeholder="Display name" value={cname} onChange={(e) => setCname(e.target.value)} />
          <input required className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Brand" value={cbrand} onChange={(e) => setCbrand(e.target.value)} />
          <input required className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Model" value={cmodel} onChange={(e) => setCmodel(e.target.value)} />
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
            <option value="">Select Category</option>
            {categories.map((c) => <option key={c.category_id} value={c.category_id}>{c.category_name}</option>)}
            <option value={NEW_OPTION_VALUE}>Add new category</option>
          </select>

          {ccat === NEW_OPTION_VALUE ? (
            <input
              required
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="New category name"
              value={cnewCategoryName}
              onChange={(e) => setCnewCategoryName(e.target.value)}
            />
          ) : (
            <select
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              value={csub}
              onChange={(e) => setCsub(e.target.value)}
              disabled={!ccat}
            >
              <option value="">Select Sub-category</option>
              {subCategories.map((s) => <option key={s.sub_category_id} value={s.sub_category_id}>{s.sub_category_name}</option>)}
              <option value={NEW_OPTION_VALUE}>Add new sub-category</option>
            </select>
          )}

          {ccat === NEW_OPTION_VALUE || csub === NEW_OPTION_VALUE ? (
            <input
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="New sub-category name (optional)"
              value={cnewSubCategoryName}
              onChange={(e) => setCnewSubCategoryName(e.target.value)}
            />
          ) : null}

          <select className="rounded-lg border border-slate-200 px-3 py-2 text-sm" value={cbranchId} onChange={(e) => setCbranchId(e.target.value)}>
            <option value="">Select branch (optional)</option>
            {branches.map((b) => (
              <option key={b.branch_id} value={b.branch_id}>
                {b.branch_name}
              </option>
            ))}
          </select>
          <input required type="number" className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="Initial quantity" value={cqty} onChange={(e) => setCqty(e.target.value)} />
        </div>

        <div className="rounded-xl border border-slate-200 p-3 space-y-3 bg-slate-50/50">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-slate-800">Specifications</h4>
            <button
              type="button"
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700"
              onClick={addSpecRow}
            >
              Add spec row
            </button>
          </div>

          <p className="text-xs text-slate-500">
            Choose an existing attribute or select Add new attribute and enter a name. This works like multi-upload rows in Swagger UI.
          </p>

          {specRows.map((row) => (
            <div key={row.id} className="grid grid-cols-1 md:grid-cols-12 gap-2 items-start">
              <select
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-5 bg-white"
                value={row.attributeRef}
                onChange={(e) => updateSpecRow(row.id, { attributeRef: e.target.value, newAttributeName: e.target.value === '__new__' ? row.newAttributeName : '' })}
                disabled={!csub}
              >
                <option value="">Select attribute</option>
                {attributeOptions.map((item) => (
                  <option key={item.attribute_id} value={item.attribute_id}>
                    {item.attribute_name}
                  </option>
                ))}
                <option value="__new__">Add new attribute</option>
              </select>

              {row.attributeRef === '__new__' ? (
                <input
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-3"
                  placeholder="New attribute name"
                  value={row.newAttributeName}
                  onChange={(e) => updateSpecRow(row.id, { newAttributeName: e.target.value })}
                />
              ) : (
                <div className="md:col-span-3" />
              )}

              <input
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-3"
                placeholder="Value"
                value={row.value}
                onChange={(e) => updateSpecRow(row.id, { value: e.target.value })}
              />

              <button
                type="button"
                className="rounded-lg border border-rose-200 px-2 py-2 text-xs font-medium text-rose-700 md:col-span-1 bg-white"
                onClick={() => removeSpecRow(row.id)}
                aria-label="Remove specification row"
              >
                Remove
              </button>
            </div>
          ))}

          {!csub ? (
            <p className="text-xs text-amber-700">Select a sub-category to load existing attribute options.</p>
          ) : null}
        </div>

        <button type="submit" disabled={createMut.isPending} className="rounded-xl bg-slate-900 text-white text-sm font-medium px-4 py-2 w-full disabled:opacity-50">
          Create
        </button>
        {createMut.isError ? <p className="text-xs text-rose-600">{createMut.error?.message}</p> : null}
      </form>
    </div>
  )
}

