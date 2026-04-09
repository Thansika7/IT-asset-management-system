import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Pagination from '@/components/Pagination'
import { apiFetch } from '@/lib/api'
import CmdbDependencyMap from '@/components/CmdbDependencyMap'
import { GitBranch, RefreshCw, Plus } from 'lucide-react'

const REL_LABELS = {
  depends_on: 'Depends on',
  connected_to: 'Connected to',
  assigned_to: 'Assigned to',
  hosted_on: 'Hosted on',
}

export default function CMDB() {
  const qc = useQueryClient()
  const [filterCiId, setFilterCiId] = useState('')
  const [itemSearch, setItemSearch] = useState('')
  const [itemType, setItemType] = useState('')
  const [relSearch, setRelSearch] = useState('')
  const [relType, setRelType] = useState('')
  const [ciPage, setCiPage] = useState(1)
  const [relPage, setRelPage] = useState(1)
  const [createCiType, setCreateCiType] = useState('')
  const [createCiName, setCreateCiName] = useState('')
  const [createCiAssetId, setCreateCiAssetId] = useState('')
  const [createCiStatus, setCreateCiStatus] = useState('ACTIVE')
  const [sourceCi, setSourceCi] = useState('')
  const [targetCi, setTargetCi] = useState('')
  const [createRelType, setCreateRelType] = useState('')
  const PAGE_SIZE = 10

  const itemQueryString = useMemo(() => {
    const params = new URLSearchParams({ page: String(ciPage), per_page: String(PAGE_SIZE) })
    if (itemSearch.trim()) params.set('search', itemSearch.trim())
    if (itemType) params.set('ci_type', itemType)
    return params.toString()
  }, [ciPage, itemSearch, itemType])

  const relQueryString = useMemo(() => {
    const params = new URLSearchParams({ page: String(relPage), per_page: String(PAGE_SIZE) })
    if (filterCiId) params.set('ci_id', filterCiId)
    if (relSearch.trim()) params.set('search', relSearch.trim())
    if (relType) params.set('relationship_type', relType)
    return params.toString()
  }, [relPage, filterCiId, relSearch, relType])

  const itemsQuery = useQuery({
    queryKey: ['cmdb-items', itemQueryString],
    queryFn: () => apiFetch(`/cmdb/items?${itemQueryString}`),
  })

  const relQuery = useQuery({
    queryKey: ['cmdb-relationships', relQueryString],
    queryFn: () => apiFetch(`/cmdb/relationships?${relQueryString}`),
  })

  const allItemsQuery = useQuery({
    queryKey: ['cmdb-items-all'],
    queryFn: () => apiFetch('/cmdb/items?page=1&per_page=1000'),
  })

  const optionsQuery = useQuery({
    queryKey: ['cmdb-options'],
    queryFn: () => apiFetch('/cmdb/options'),
  })

  const assetsQuery = useQuery({
    queryKey: ['cmdb-assets'],
    queryFn: () => apiFetch('/assets/options'),
  })

  /** Full edge list for the dependency map (table filter does not shrink the graph). */
  const relAllQuery = useQuery({
    queryKey: ['cmdb-relationships-all'],
    queryFn: () => apiFetch('/cmdb/relationships'),
  })

  const items = itemsQuery.data?.items || []
  const relationships = relQuery.data?.items || []
  const itemTotal = itemsQuery.data?.total || 0
  const relTotal = relQuery.data?.total || 0
  const allItems = allItemsQuery.data?.items || []
  const assetOptions = assetsQuery.data || []
  const allRelationships = relAllQuery.data || []

  const ciTotalPages = Math.max(1, Math.ceil(itemTotal / PAGE_SIZE))
  const relTotalPages = Math.max(1, Math.ceil(relTotal / PAGE_SIZE))

  const relTypeOptions = useMemo(() => {
    return optionsQuery.data?.relationship_types || []
  }, [optionsQuery.data])

  const ciTypeOptions = useMemo(() => {
    return optionsQuery.data?.ci_types || []
  }, [optionsQuery.data])

  const createCiMut = useMutation({
    mutationFn: (body) => apiFetch('/cmdb/items', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cmdb-items'] })
      qc.invalidateQueries({ queryKey: ['cmdb-items-all'] })
      qc.invalidateQueries({ queryKey: ['cmdb-relationships-all'] })
      setCreateCiName('')
      setCreateCiAssetId('')
      setCreateCiType('')
      setCreateCiStatus('ACTIVE')
    },
  })

  const createRelMut = useMutation({
    mutationFn: (body) => apiFetch('/cmdb/relationships', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cmdb-relationships'] })
      qc.invalidateQueries({ queryKey: ['cmdb-relationships-all'] })
      setSourceCi('')
      setTargetCi('')
      setCreateRelType('')
    },
  })

  const idToItem = useMemo(() => {
    const m = new Map()
    for (const it of items) {
      m.set(it.ci_id, it)
    }
    return m
  }, [items])

  const formatEnd = (ciId) => {
    const it = idToItem.get(ciId)
    if (!it) return { title: ciId, sub: '—' }
    return { title: it.name, sub: `${it.ci_type} · ${it.ci_id}` }
  }

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <GitBranch className="w-7 h-7 text-teal-600" />
            CMDB
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Configuration items and how they relate (<span className="font-mono text-xs">depends_on</span>,{' '}
            <span className="font-mono text-xs">connected_to</span>, etc.). Data comes from{' '}
            <span className="font-mono text-xs">/cmdb/items</span> and <span className="font-mono text-xs">/cmdb/relationships</span>.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            itemsQuery.refetch()
            relQuery.refetch()
            relAllQuery.refetch()
          }}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700"
        >
          <RefreshCw className={`w-4 h-4 ${itemsQuery.isFetching || relQuery.isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-[0.16em]">Dependency map</h2>
          <p className="text-xs text-slate-500 max-w-xl">
            Drag the canvas, use controls to zoom. Arrows follow CMDB relationships (left → right). Colors:{' '}
            <span className="text-rose-700 font-medium">depends on</span>,{' '}
            <span className="text-teal-700 font-medium">connected to</span>,{' '}
            <span className="text-violet-700 font-medium">assigned to</span>,{' '}
            <span className="text-amber-700 font-medium">hosted on</span>.
          </p>
        </div>
        {relAllQuery.isError ? (
          <p className="text-sm text-rose-600">Could not load graph data.</p>
        ) : itemsQuery.isLoading || relAllQuery.isLoading ? (
          <p className="text-sm text-slate-500 py-24 text-center">Loading map…</p>
        ) : (
          <CmdbDependencyMap items={items} relationships={allRelationships} />
        )}
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-[0.16em]">Create / Update</h2>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <form
            className="rounded-2xl border border-teal-200 bg-teal-50/30 p-4 space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              createCiMut.mutate({
                ci_type: createCiType,
                name: createCiName.trim(),
                asset_id: createCiAssetId || null,
                status: createCiStatus,
              })
            }}
          >
            <div className="flex items-center gap-2 text-teal-900 font-semibold">
              <Plus className="w-4 h-4" />
              Create CI
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={createCiType} onChange={(e) => setCreateCiType(e.target.value)}>
                <option value="">Select CI type</option>
                {ciTypeOptions.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={createCiStatus} onChange={(e) => setCreateCiStatus(e.target.value)}>
                <option value="ACTIVE">ACTIVE</option>
                <option value="INACTIVE">INACTIVE</option>
              </select>
              <input className="rounded-xl border border-slate-200 px-3 py-2 text-sm sm:col-span-2" placeholder="CI name" value={createCiName} onChange={(e) => setCreateCiName(e.target.value)} />
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm sm:col-span-2" value={createCiAssetId} onChange={(e) => setCreateCiAssetId(e.target.value)}>
                <option value="">Link to asset (optional)</option>
                {assetOptions.map((asset) => (
                  <option key={asset.asset_id} value={asset.asset_id}>{asset.name} ({asset.asset_id})</option>
                ))}
              </select>
            </div>
            {createCiMut.error ? <p className="text-xs text-rose-600">{createCiMut.error.message}</p> : null}
            <button type="submit" className="rounded-xl bg-teal-700 text-white text-sm font-semibold px-4 py-2 disabled:opacity-50" disabled={createCiMut.isPending || !createCiType || !createCiName.trim()}>
              {createCiMut.isPending ? 'Saving…' : 'Create CI'}
            </button>
          </form>

          <form
            className="rounded-2xl border border-indigo-200 bg-indigo-50/30 p-4 space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              createRelMut.mutate({
                source_ci: sourceCi,
                target_ci: targetCi,
                relationship_type: createRelType,
              })
            }}
          >
            <div className="flex items-center gap-2 text-indigo-900 font-semibold">
              <Plus className="w-4 h-4" />
              Create relationship
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={sourceCi} onChange={(e) => setSourceCi(e.target.value)}>
                <option value="">Source CI</option>
                {allItems.map((item) => <option key={item.ci_id} value={item.ci_id}>{item.name} ({item.ci_id})</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm" value={targetCi} onChange={(e) => setTargetCi(e.target.value)}>
                <option value="">Target CI</option>
                {allItems.map((item) => <option key={item.ci_id} value={item.ci_id}>{item.name} ({item.ci_id})</option>)}
              </select>
              <select className="rounded-xl border border-slate-200 px-3 py-2 text-sm sm:col-span-2" value={createRelType} onChange={(e) => setCreateRelType(e.target.value)}>
                <option value="">Relationship type</option>
                {relTypeOptions.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </div>
            {createRelMut.error ? <p className="text-xs text-rose-600">{createRelMut.error.message}</p> : null}
            <button type="submit" className="rounded-xl bg-indigo-700 text-white text-sm font-semibold px-4 py-2 disabled:opacity-50" disabled={createRelMut.isPending || !sourceCi || !targetCi || !createRelType}>
              {createRelMut.isPending ? 'Saving…' : 'Create relationship'}
            </button>
          </form>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-[0.16em]">Configuration items</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Search name, CI ID, asset link..."
            value={itemSearch}
            onChange={(e) => {
              setItemSearch(e.target.value)
              setCiPage(1)
            }}
          />
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={itemType}
            onChange={(e) => {
              setItemType(e.target.value)
              setCiPage(1)
            }}
          >
            <option value="">All CI types</option>
            {ciTypeOptions.map((type) => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>
        {itemsQuery.isError ? (
          <p className="text-sm text-rose-600">Could not load items.</p>
        ) : itemsQuery.isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-500">No configuration items yet. Seed data or create via API / admin tools.</p>
        ) : (
          <>
            <div className="overflow-x-auto rounded-2xl border border-slate-100">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">CI ID</th>
                    <th className="px-4 py-3">Asset link</th>
                    <th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it) => (
                    <tr key={it.ci_id} className="border-t border-slate-100 hover:bg-slate-50/80">
                      <td className="px-4 py-3 font-medium text-slate-900">{it.name}</td>
                      <td className="px-4 py-3 text-slate-600">{it.ci_type}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-600">{it.ci_id}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-500">{it.asset_id || '—'}</td>
                      <td className="px-4 py-3 text-slate-600">{it.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={ciPage} totalPages={ciTotalPages} onPageChange={setCiPage} pageSize={PAGE_SIZE} total={itemTotal} />
          </>
        )}
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-[0.16em]">Relationships</h2>
          <div className="flex items-center gap-2 flex-wrap">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Filter by CI</label>
            <select
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm min-w-[200px]"
              value={filterCiId}
              onChange={(e) => {
                setFilterCiId(e.target.value)
                setRelPage(1)
              }}
            >
              <option value="">All relationships</option>
              {items.map((it) => (
                <option key={it.ci_id} value={it.ci_id}>
                  {it.name} ({it.ci_id})
                </option>
              ))}
            </select>
            <select
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm min-w-[200px]"
              value={relType}
              onChange={(e) => {
                setRelType(e.target.value)
                setRelPage(1)
              }}
            >
              <option value="">All relationship types</option>
              {relTypeOptions.map((type) => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
            <input
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm min-w-[220px]"
              placeholder="Search source/target/type/id..."
              value={relSearch}
              onChange={(e) => {
                setRelSearch(e.target.value)
                setRelPage(1)
              }}
            />
          </div>
        </div>
        {relQuery.isError ? (
          <p className="text-sm text-rose-600">Could not load relationships.</p>
        ) : relQuery.isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : relationships.length === 0 ? (
          <p className="text-sm text-slate-500">No relationships for this filter.</p>
        ) : (
          <>
            <div className="overflow-x-auto rounded-2xl border border-slate-100">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-3">Relationship</th>
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3 w-8" />
                    <th className="px-4 py-3">Target</th>
                    <th className="px-4 py-3">Rel. ID</th>
                  </tr>
                </thead>
                <tbody>
                  {relationships.map((rel) => {
                    const src = formatEnd(rel.source_ci)
                    const tgt = formatEnd(rel.target_ci)
                    const label = REL_LABELS[rel.relationship_type] || rel.relationship_type
                    return (
                      <tr key={rel.relationship_id} className="border-t border-slate-100 hover:bg-teal-50/40">
                        <td className="px-4 py-3">
                          <span className="inline-flex rounded-lg bg-teal-50 text-teal-800 px-2 py-0.5 text-xs font-semibold">
                            {label}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-slate-900">{src.title}</div>
                          <div className="text-xs text-slate-500 font-mono">{rel.source_ci}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-center">→</td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-slate-900">{tgt.title}</div>
                          <div className="text-xs text-slate-500 font-mono">{rel.target_ci}</div>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-slate-400">{rel.relationship_id}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={relPage} totalPages={relTotalPages} onPageChange={setRelPage} pageSize={PAGE_SIZE} total={relTotal} />
          </>
        )}
      </section>
    </div>
  )
}
