import React, { useMemo, useState } from 'react'
import Pagination from '@/components/Pagination'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import CmdbDependencyMap from '@/components/CmdbDependencyMap'
import { GitBranch, RefreshCw } from 'lucide-react'

const REL_LABELS = {
  depends_on: 'Depends on',
  connected_to: 'Connected to',
  assigned_to: 'Assigned to',
  hosted_on: 'Hosted on',
}

export default function CMDB() {
  const [filterCiId, setFilterCiId] = useState('')

  const itemsQuery = useQuery({
    queryKey: ['cmdb-items'],
    queryFn: () => apiFetch('/cmdb/items'),
  })

  const relQuery = useQuery({
    queryKey: ['cmdb-relationships', filterCiId],
    queryFn: () => {
      const q = filterCiId ? `?ci_id=${encodeURIComponent(filterCiId)}` : ''
      return apiFetch(`/cmdb/relationships${q}`)
    },
  })

  /** Full edge list for the dependency map (table filter does not shrink the graph). */
  const relAllQuery = useQuery({
    queryKey: ['cmdb-relationships-all'],
    queryFn: () => apiFetch('/cmdb/relationships'),
  })

  const items = itemsQuery.data || []
  const relationships = relQuery.data || []
  const allRelationships = relAllQuery.data || []

  const [ciPage, setCiPage] = useState(1)
  const [relPage, setRelPage] = useState(1)
  const PAGE_SIZE = 10

  const ciTotalPages = Math.ceil(items.length / PAGE_SIZE)
  const pagedItems = useMemo(() => {
    const s = (ciPage - 1) * PAGE_SIZE
    return items.slice(s, s + PAGE_SIZE)
  }, [items, ciPage, PAGE_SIZE])

  const relTotalPages = Math.ceil(relationships.length / PAGE_SIZE)
  const pagedRels = useMemo(() => {
    const s = (relPage - 1) * PAGE_SIZE
    return relationships.slice(s, s + PAGE_SIZE)
  }, [relationships, relPage, PAGE_SIZE])

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
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-[0.16em]">Configuration items</h2>
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
                  {pagedItems.map((it) => (
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
            <Pagination page={ciPage} totalPages={ciTotalPages} onPageChange={setCiPage} pageSize={PAGE_SIZE} total={items.length} />
          </>
        )}
      </section>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h2 className="text-sm font-bold text-slate-900 uppercase tracking-[0.16em]">Relationships</h2>
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Filter by CI</label>
            <select
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm min-w-[200px]"
              value={filterCiId}
              onChange={(e) => setFilterCiId(e.target.value)}
            >
              <option value="">All relationships</option>
              {items.map((it) => (
                <option key={it.ci_id} value={it.ci_id}>
                  {it.name} ({it.ci_id})
                </option>
              ))}
            </select>
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
                  {pagedRels.map((rel) => {
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
            <Pagination page={relPage} totalPages={relTotalPages} onPageChange={setRelPage} pageSize={PAGE_SIZE} total={relationships.length} />
          </>
        )}
      </section>
    </div>
  )
}
