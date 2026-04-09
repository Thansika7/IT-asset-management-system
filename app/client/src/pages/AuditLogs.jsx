import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, RefreshCw } from 'lucide-react'
import Pagination from '@/components/Pagination'
import { apiFetch } from '@/lib/api'

export default function AuditLogs() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [tableName, setTableName] = useState('')
  const PAGE_SIZE = 20

  const query = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      per_page: String(PAGE_SIZE),
    })
    if (search.trim()) params.set('search', search.trim())
    if (tableName.trim()) params.set('table_name', tableName.trim())
    return params.toString()
  }, [page, search, tableName])

  const { data, isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ['audit-logs', query],
    queryFn: () => apiFetch(`/audit/logs?${query}`),
  })

  const { data: tableOptions = [] } = useQuery({
    queryKey: ['audit-table-options'],
    queryFn: () => apiFetch('/audit/tables'),
  })

  const items = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Audit Logs</h1>
          <p className="text-sm text-slate-600 mt-1">Trace changes across records with actor, reason, and before/after values.</p>
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

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="relative md:col-span-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              className="w-full rounded-xl border border-slate-200 pl-10 pr-3 py-2 text-sm"
              placeholder="Search by table, record id, action, actor, or reason..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
          </div>
          <select
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm"
            value={tableName}
            onChange={(e) => {
              setTableName(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All tables</option>
            {tableOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-14 text-center text-slate-400 animate-pulse">Loading audit logs...</div>
        ) : isError ? (
          <div className="p-6 text-sm text-rose-700">{error?.message}</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1080px] text-sm">
                <thead className="bg-slate-50 text-slate-500 uppercase text-[11px] tracking-[0.16em]">
                  <tr>
                    <th className="text-left px-4 py-3">When</th>
                    <th className="text-left px-4 py-3">Action</th>
                    <th className="text-left px-4 py-3">Table</th>
                    <th className="text-left px-4 py-3">Record</th>
                    <th className="text-left px-4 py-3">Changed By</th>
                    <th className="text-left px-4 py-3">Role</th>
                    <th className="text-left px-4 py-3">Reason</th>
                    <th className="text-left px-4 py-3">Old Values</th>
                    <th className="text-left px-4 py-3">New Values</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((row) => (
                    <tr key={row.audit_id}>
                      <td className="px-4 py-3 text-slate-700 whitespace-nowrap">{row.changed_at ? new Date(row.changed_at).toLocaleString() : '—'}</td>
                      <td className="px-4 py-3 text-slate-800 font-semibold">{row.action || '—'}</td>
                      <td className="px-4 py-3 text-slate-700">{row.table_name || '—'}</td>
                      <td className="px-4 py-3 text-slate-600 font-mono text-xs">{row.record_id || '—'}</td>
                      <td className="px-4 py-3 text-slate-700">{row.changed_by || 'SYSTEM'}</td>
                      <td className="px-4 py-3 text-slate-600">{row.user_role || '—'}</td>
                      <td className="px-4 py-3 text-slate-600">{row.reason || '—'}</td>
                      <td className="px-4 py-3 text-slate-600 font-mono text-xs whitespace-pre-wrap">{row.old_values ? JSON.stringify(row.old_values) : '—'}</td>
                      <td className="px-4 py-3 text-slate-600 font-mono text-xs whitespace-pre-wrap">{row.new_values ? JSON.stringify(row.new_values) : '—'}</td>
                    </tr>
                  ))}
                  {items.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="px-4 py-14 text-center text-slate-400">No audit entries found.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} pageSize={PAGE_SIZE} total={total} />
          </>
        )}
      </div>
    </div>
  )
}
