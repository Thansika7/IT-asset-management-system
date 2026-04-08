
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { apiFetch } from '@/lib/api'
import {
  R,
  canTriage,
  canHrReview,
  canManagerReview,
  canAdminReview,
  canExecuteRequest,
  canResolveService,
  canTransferCrossBranch,
  canNecessityRecommendation,
} from '@/lib/roles'
import { Eye, Plus, RefreshCw, Search, Sparkles } from 'lucide-react'
import ConfirmDialog from '@/components/ConfirmDialog'

const SEVERITY_OPTIONS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
const PRIORITY_OPTIONS = ['P1', 'P2', 'P3', 'P4']
const SEVERITY_HELP = {
  CRITICAL: 'Complete system failure',
  HIGH: 'Major functionality affected',
  MEDIUM: 'Partial impact',
  LOW: 'Minor issue',
}
const PRIORITY_RESPONSE_TIME = {
  P1: '< 1 hour',
  P2: '< 4 hours',
  P3: '< 24 hours',
  P4: '2-3 days',
}
const URGENCY_RESPONSE_TIME = {
  HIGH: '< 1 hour',
  MEDIUM: '< 4 hours',
  LOW: '< 24 hours',
}

function Badge({ children, tone = 'slate', className = '' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
    amber: 'bg-amber-50 text-amber-800 border-amber-200',
    emerald: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    rose: 'bg-rose-50 text-rose-800 border-rose-200',
    violet: 'bg-violet-50 text-violet-800 border-violet-200',
    cyan: 'bg-cyan-50 text-cyan-800 border-cyan-200',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-lg text-[11px] font-semibold uppercase tracking-wide border ${tones[tone]} ${className}`}>
      {children}
    </span>
  )
}

function stageTone(stage) {
  if (!stage) return 'slate'
  if (stage === 'COMPLETED') return 'emerald'
  if (stage === 'REJECTED') return 'rose'
  if (String(stage).includes('APPROVAL') || stage === 'HR_VERIFICATION') return 'amber'
  if (stage === 'READY' || stage === 'IN_REPAIR') return 'violet'
  return 'cyan'
}

function priorityTone(priority) {
  if (priority === 'P1') return 'rose'
  if (priority === 'P2') return 'amber'
  if (priority === 'P3') return 'cyan'
  return 'emerald'
}

function severityTone(severity) {
  if (severity === 'CRITICAL') return 'rose'
  if (severity === 'HIGH') return 'amber'
  if (severity === 'MEDIUM') return 'cyan'
  return 'emerald'
}

function deriveUrgencyPreview({ severity, affectedUsers, actionType, reason, assetCategory, assetName }) {
  const text = `${assetName || ''} ${reason || ''}`.toLowerCase()
  const category = (assetCategory || '').toLowerCase()
  const action = (actionType || '').toUpperCase()

  if (severity === 'CRITICAL') return 'HIGH'
  if (affectedUsers >= 10) return 'HIGH'
  if (['production down', 'not powering on', 'not turning on', 'network outage', 'cannot login', 'service disruption'].some((term) => text.includes(term))) return 'HIGH'
  if (['server', 'network', 'security'].some((term) => category.includes(term))) return 'HIGH'
  if (action === 'SERVICE' && severity === 'HIGH') return 'HIGH'
  if (severity === 'HIGH') return 'MEDIUM'
  if (action === 'NEW' && ['onboarding', 'new joiner', 'starter kit'].some((term) => text.includes(term))) return 'MEDIUM'
  if (['mouse', 'keyboard', 'accessory'].some((term) => category.includes(term))) return 'LOW'
  return severity === 'LOW' ? 'LOW' : 'MEDIUM'
}

function computePriorityPreview(severity, urgency) {
  const matrix = {
    'CRITICAL:HIGH': 'P1',
    'CRITICAL:MEDIUM': 'P1',
    'CRITICAL:LOW': 'P2',
    'HIGH:HIGH': 'P1',
    'HIGH:MEDIUM': 'P2',
    'HIGH:LOW': 'P3',
    'MEDIUM:HIGH': 'P2',
    'MEDIUM:MEDIUM': 'P3',
    'MEDIUM:LOW': 'P4',
    'LOW:HIGH': 'P3',
    'LOW:MEDIUM': 'P4',
    'LOW:LOW': 'P4',
  }
  return matrix[`${severity}:${urgency}`] || 'P3'
}

function formatDate(value) {
  if (!value) return 'Not available'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

function prettyBool(value) {
  if (value === true) return 'Yes'
  if (value === false) return 'No'
  return 'Pending'
}

function NewRequestForm({ onCreate, busy, options }) {
  const fallbackCategories = useMemo(() => {
    const raw = options?.categories?.length
      ? options.categories
      : ['Laptop', 'Monitor', 'Keyboard', 'Mouse', 'Printer', 'Phone', 'Accessory', 'Software', 'Other']
    const other = raw.filter((x) => String(x).toLowerCase() === 'other')
    const rest = raw.filter((x) => String(x).toLowerCase() !== 'other').sort((a, b) => String(a).localeCompare(String(b)))
    return [...rest, ...other]
  }, [options?.categories])
  const knownAssets = options?.known_assets ?? []
  const [assetCategory, setAssetCategory] = useState(fallbackCategories[0] || 'Laptop')
  const [reasonText, setReasonText] = useState('')
  const [selectedKnownAsset, setSelectedKnownAsset] = useState('')
  const [assetName, setAssetName] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [submittedSearch, setSubmittedSearch] = useState('')
  const [suggestHighlight, setSuggestHighlight] = useState(-1)
  const suggestHighlightRef = useRef(-1)
  const [selectedCategoryId, setSelectedCategoryId] = useState('')
  const [selectedSubCategoryId, setSelectedSubCategoryId] = useState('')

  const sortedKnownAssets = useMemo(() => {
    return [...knownAssets].sort((a, b) => String(a.asset_name || '').localeCompare(String(b.asset_name || '')))
  }, [knownAssets])

  const categoriesQuery = useQuery({
    queryKey: ['discover-categories'],
    queryFn: () => apiFetch('/categories'),
  })

  const sortedApiCategories = useMemo(() => {
    const raw = categoriesQuery.data || []
    return [...raw].sort((a, b) => String(a.category_name).localeCompare(String(b.category_name)))
  }, [categoriesQuery.data])

  const hasApiCategories = sortedApiCategories.length > 0

  const effectiveCategoryId = useMemo(() => {
    if (!sortedApiCategories.length) return ''
    return selectedCategoryId || sortedApiCategories[0].category_id
  }, [selectedCategoryId, sortedApiCategories])

  const subCategoriesQuery = useQuery({
    queryKey: ['discover-subcategories', effectiveCategoryId],
    queryFn: () => apiFetch(`/categories/${encodeURIComponent(effectiveCategoryId)}/subcategories`),
    enabled: Boolean(effectiveCategoryId),
  })

  const sortedSubcategories = useMemo(() => {
    const raw = subCategoriesQuery.data || []
    return [...raw].sort((a, b) => String(a.sub_category_name).localeCompare(String(b.sub_category_name)))
  }, [subCategoriesQuery.data])

  const categoryAssetsQuery = useQuery({
    queryKey: ['discover-assets-by-subcategory', selectedSubCategoryId],
    queryFn: () => apiFetch(`/subcategories/${encodeURIComponent(selectedSubCategoryId)}/assets`),
    enabled: Boolean(selectedSubCategoryId),
  })

  useEffect(() => {
    if (!hasApiCategories || selectedCategoryId) return
    const first = sortedApiCategories[0]
    setSelectedCategoryId(first.category_id)
    setAssetCategory(first.category_name)
  }, [hasApiCategories, sortedApiCategories, selectedCategoryId])

  const suggestionsQuery = useQuery({
    queryKey: ['discover-suggestions', searchInput],
    queryFn: () => apiFetch(`/search/suggestions?q=${encodeURIComponent(searchInput)}`),
    enabled: searchInput.trim().length >= 2,
  })
  const popularQuery = useQuery({
    queryKey: ['discover-popular'],
    queryFn: () => apiFetch('/search/popular'),
  })
  const recentQuery = useQuery({
    queryKey: ['discover-recent'],
    queryFn: () => apiFetch('/search/recent'),
  })
  const searchResultsQuery = useQuery({
    queryKey: ['discover-search', submittedSearch],
    queryFn: () => apiFetch(`/search?q=${encodeURIComponent(submittedSearch)}`),
    enabled: submittedSearch.trim().length >= 2,
  })

  useEffect(() => {
    setSelectedSubCategoryId('')
  }, [selectedCategoryId])

  const matchingKnownAsset = useMemo(() => {
    const typed = assetName.trim().toLowerCase()
    if (!typed) return null
    return knownAssets.find((item) => item.asset_name.toLowerCase() === typed) || null
  }, [assetName, knownAssets])

  useEffect(() => {
    if (selectedKnownAsset) {
      const match = knownAssets.find((item) => item.asset_name === selectedKnownAsset)
      if (match) {
        setAssetName(match.asset_name)
        if (match.category) {
          setAssetCategory(match.category)
          const apiCat = sortedApiCategories.find((c) => c.category_name === match.category)
          if (apiCat) setSelectedCategoryId(apiCat.category_id)
        }
      }
    }
  }, [selectedKnownAsset, knownAssets, sortedApiCategories])

  useEffect(() => {
    if (!selectedKnownAsset && matchingKnownAsset?.category && assetCategory === 'Other') {
      setAssetCategory(matchingKnownAsset.category)
    }
  }, [selectedKnownAsset, matchingKnownAsset, assetCategory])

  const submit = (e) => {
    e.preventDefault()
    const resolvedAssetName = assetName.trim() || selectedKnownAsset.trim()
    const inferredCategory = matchingKnownAsset?.category || assetCategory
    const resolvedCategory = inferredCategory === 'Other' && matchingKnownAsset?.category ? matchingKnownAsset.category : inferredCategory
    const resolvedReason = reasonText.trim()

    onCreate({
      asset_name: resolvedAssetName || `${resolvedCategory} request`,
      asset_category: resolvedCategory,
      reason: resolvedReason,
    })

    setSelectedKnownAsset('')
    setAssetName('')
    setReasonText('')
    if (hasApiCategories && sortedApiCategories[0]) {
      setSelectedCategoryId(sortedApiCategories[0].category_id)
      setAssetCategory(sortedApiCategories[0].category_name)
    } else {
      setAssetCategory(fallbackCategories[0] || 'Laptop')
    }
    setSelectedSubCategoryId('')
    setSearchInput('')
    setSubmittedSearch('')
    suggestHighlightRef.current = -1
    setSuggestHighlight(-1)
  }

  const applySuggestedAsset = (item) => {
    if (!item) return
    setAssetName(item.asset_name || '')
    if (item.category) {
      setAssetCategory(item.category)
      const apiCat = sortedApiCategories.find((c) => c.category_name === item.category)
      if (apiCat) setSelectedCategoryId(apiCat.category_id)
    }
    setSelectedKnownAsset(item.asset_name || '')
  }

  const defaultSuggestions = useMemo(() => {
    if (searchInput.trim().length >= 2) return suggestionsQuery.data || []
    const popular = popularQuery.data || []
    const recent = recentQuery.data || []
    const merged = []
    const seen = new Set()
    for (const item of [...recent, ...popular]) {
      const key = item.asset_id || item.asset_name
      if (key && !seen.has(key)) {
        seen.add(key)
        merged.push(item)
      }
    }
    return merged.slice(0, 10)
  }, [searchInput, suggestionsQuery.data, popularQuery.data, recentQuery.data])

  useEffect(() => {
    suggestHighlightRef.current = -1
    setSuggestHighlight(-1)
  }, [searchInput])

  const onSearchKeyDown = (e) => {
    const list = defaultSuggestions
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!list.length) return
      setSuggestHighlight((i) => {
        const next = i < 0 ? 0 : Math.min(list.length - 1, i + 1)
        suggestHighlightRef.current = next
        return next
      })
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (!list.length) return
      setSuggestHighlight((i) => {
        const next = Math.max(-1, i - 1)
        suggestHighlightRef.current = next
        return next
      })
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      suggestHighlightRef.current = -1
      setSuggestHighlight(-1)
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      const idx = suggestHighlightRef.current
      if (idx >= 0 && list[idx]) {
        applySuggestedAsset(list[idx])
        suggestHighlightRef.current = -1
        setSuggestHighlight(-1)
        return
      }
      if (searchInput.trim().length >= 2) {
        setSubmittedSearch(searchInput.trim())
      }
    }
  }

  return (
    <form onSubmit={submit} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-5 motion-fade-up surface-sheen">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Create Request</h2>
          <p className="text-sm text-slate-600 mt-1">Choose a category and reason from the guided list. If your asset is already known to the system, type or pick its name and the form will load what it can automatically.</p>
        </div>
        <Badge tone="cyan">For Employees</Badge>
      </div>

      {hasApiCategories ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Category</label>
            <select
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
              value={selectedCategoryId || sortedApiCategories[0]?.category_id || ''}
              onChange={(e) => {
                const id = e.target.value
                setSelectedCategoryId(id)
                const cat = sortedApiCategories.find((c) => c.category_id === id)
                if (cat) setAssetCategory(cat.category_name)
              }}
            >
              {sortedApiCategories.map((cat) => (
                <option key={cat.category_id} value={cat.category_id}>
                  {cat.category_name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Subcategory</label>
            <select
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
              value={selectedSubCategoryId}
              onChange={(e) => setSelectedSubCategoryId(e.target.value)}
              disabled={!(selectedCategoryId || sortedApiCategories[0]?.category_id)}
            >
              <option value="">{selectedCategoryId || sortedApiCategories[0]?.category_id ? 'Subcategory (optional)' : '—'}</option>
              {sortedSubcategories.map((sub) => (
                <option key={sub.sub_category_id} value={sub.sub_category_id}>
                  {sub.sub_category_name}
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Category</label>
          <select
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm max-w-xl"
            value={assetCategory}
            onChange={(e) => setAssetCategory(e.target.value)}
            disabled={categoriesQuery.isLoading}
          >
            {fallbackCategories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          {categoriesQuery.isLoading ? (
            <p className="text-[11px] text-slate-500">Loading catalog categories…</p>
          ) : (
            <p className="text-[11px] text-slate-500">Catalog categories unavailable; using guided list from the server.</p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Search assets</label>
          <div className="flex gap-2">
            <input
              className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
              placeholder="Type at least 2 chars (e.g. laptop, laptp)"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={onSearchKeyDown}
              autoComplete="off"
              aria-autocomplete="list"
              aria-expanded={defaultSuggestions.length > 0}
            />
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded-2xl border border-slate-300 px-3 py-2 text-sm font-semibold"
              onClick={() => setSubmittedSearch(searchInput.trim())}
              disabled={searchInput.trim().length < 2}
            >
              <Search className="w-4 h-4" />
              Search
            </button>
          </div>
          <p className="text-[11px] text-slate-500">Use ↑↓ to move in the list, Enter to pick a row or run search (Enter does not submit the request from this field).</p>
          {defaultSuggestions.length > 0 ? (
            <div className="w-full min-w-full rounded-2xl border border-slate-200 bg-slate-50 max-h-56 overflow-auto">
              {defaultSuggestions.map((item, idx) => (
                <button
                  key={`${item.asset_id || item.asset_name}-sg`}
                  type="button"
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-slate-100 ${idx === suggestHighlight ? 'bg-slate-200' : ''}`}
                  onMouseEnter={() => {
                    suggestHighlightRef.current = idx
                    setSuggestHighlight(idx)
                  }}
                  onClick={() => {
                    suggestHighlightRef.current = -1
                    setSuggestHighlight(-1)
                    applySuggestedAsset(item)
                  }}
                >
                  <span className="font-medium text-slate-900">{item.asset_name}</span>
                  <span className="text-xs text-slate-500"> · {item.category || 'Unknown'} {item.sub_category ? `· ${item.sub_category}` : ''}</span>
                </button>
              ))}
            </div>
          ) : null}
          {submittedSearch && searchResultsQuery.data?.total === 0 ? (
            <p className="text-xs text-amber-700">
              No direct match. {searchResultsQuery.data?.did_you_mean?.length ? `Did you mean: ${searchResultsQuery.data.did_you_mean.join(', ')}` : 'Try another keyword.'}
            </p>
          ) : null}
          {submittedSearch && searchResultsQuery.data?.items?.length ? (
            <div className="rounded-2xl border border-teal-200 bg-teal-50 p-2">
              {searchResultsQuery.data.items.map((item) => (
                <button
                  key={`${item.asset_id || item.asset_name}-res`}
                  type="button"
                  className="w-full text-left px-2 py-1.5 text-sm hover:bg-white rounded"
                  onClick={() => applySuggestedAsset(item)}
                >
                  {item.asset_name} <span className="text-xs text-slate-500">({item.category || 'Unknown'})</span>
                </button>
              ))}
            </div>
          ) : null}
          {sortedKnownAssets.length ? (
            <select className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm" value={selectedKnownAsset} onChange={(e) => setSelectedKnownAsset(e.target.value)}>
              <option value="">Or pick from known assets</option>
              {sortedKnownAssets.map((item) => (
                <option key={`${item.asset_id || item.asset_name}`} value={item.asset_name}>
                  {item.asset_name}{item.category ? ` · ${item.category}` : ''}{item.owned_by_requester ? ' · My asset' : ''}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Asset name</label>
          <input
            className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm"
            placeholder="Type asset name only when needed"
            value={assetName}
            onChange={(e) => {
              setSelectedKnownAsset('')
              setAssetName(e.target.value)
            }}
            required={false}
          />
          {matchingKnownAsset ? (
            <p className="text-xs text-cyan-700">Matched existing asset. Category loaded as {matchingKnownAsset.category || 'Unknown'}.</p>
          ) : (
            <p className="text-xs text-slate-500">If the name matches existing data, category details are filled automatically.</p>
          )}
        </div>
      </div>

      {selectedSubCategoryId && (categoryAssetsQuery.data || []).length > 0 ? (
        <div className="w-full rounded-2xl border border-slate-200 bg-slate-50 max-h-52 overflow-auto">
          {(categoryAssetsQuery.data || []).slice(0, 10).map((asset) => (
            <button
              key={asset.asset_id}
              type="button"
              className="w-full text-left px-3 py-2 text-sm hover:bg-slate-100"
              onClick={() => applySuggestedAsset({ asset_name: asset.name, category: asset.category, sub_category: asset.sub_category, asset_id: asset.asset_id })}
            >
              {asset.name} <span className="text-xs text-slate-500">· {asset.asset_id}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="space-y-2 max-w-2xl">
        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Reason</label>
        <textarea
          className="w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm min-h-[110px]"
          placeholder="Describe what is needed and why."
          value={reasonText}
          onChange={(e) => setReasonText(e.target.value)}
          required
        />
        <p className="text-[11px] text-slate-500">Use plain text here. The request workflow will use this as the reason.</p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
        <p className="font-medium text-slate-800">What happens next</p>
        <p className="mt-1">Support will classify the request as NEW, SERVICE, or REPLACE. Urgency is also derived automatically by the system based on the issue and impact, so the employee does not need to guess it.</p>
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 text-white text-sm font-semibold px-5 py-3 disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          Submit Request
        </button>
      </div>
    </form>
  )
}


function RequestFilters({ draft, onChange, onApply, onClear, count }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm space-y-4 motion-fade-up motion-delay-1">
      <div>
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-[0.16em]">Filters</h2>
        <p className="text-xs text-slate-500 mt-1">{count} matching request{count === 1 ? '' : 's'}</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Priority</label>
          <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={draft.priority} onChange={(e) => onChange('priority', e.target.value)}>
            <option value="">All</option>
            {PRIORITY_OPTIONS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Severity</label>
          <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={draft.severity} onChange={(e) => onChange('severity', e.target.value)}>
            <option value="">All</option>
            {SEVERITY_OPTIONS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Urgency</label>
          <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={draft.urgency} onChange={(e) => onChange('urgency', e.target.value)}>
            <option value="">All</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="LOW">LOW</option>
          </select>
        </div>
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Request type</label>
          <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={draft.request_type} onChange={(e) => onChange('request_type', e.target.value)}>
            <option value="">All</option>
            <option value="ASSET">Asset</option>
          </select>
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button type="button" className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em]" onClick={onApply}>Apply filters</button>
        <button type="button" className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em]" onClick={onClear}>Clear</button>
      </div>
    </div>
  )
}

function RequestList({ rows, selectedId, onSelect }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-sm overflow-hidden motion-fade-up motion-delay-2">
      <div className="border-b border-slate-200 bg-slate-50 px-5 py-4">
        <div className="flex items-center gap-3">
          <Eye className="w-4 h-4 text-slate-500" />
          <div>
            <h2 className="text-lg font-bold text-slate-900">View Requests</h2>
            <p className="text-sm text-slate-600">Highest priority requests are shown first so overdue work stays visible.</p>
          </div>
        </div>
      </div>

      <div className="hidden md:grid grid-cols-[1.2fr_1fr_.8fr_.8fr_0.9fr] gap-3 px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 border-b border-slate-100">
        <span>Requester / Asset</span>
        <span>Request ID / Branch</span>
        <span>Priority</span>
        <span>Stage</span>
        <span>Status</span>
      </div>

      <div className="divide-y divide-slate-100">
        {rows.length === 0 ? (
          <p className="text-sm text-slate-500 py-10 text-center">No requests available.</p>
        ) : rows.map((row) => (
          <button
            key={row.request_id}
            type="button"
            onClick={() => onSelect(row.request_id)}
            className={`w-full text-left px-5 py-4 transition ${selectedId === row.request_id ? 'bg-cyan-50/60' : 'bg-white hover:bg-slate-50'}`}
          >
            <div className="grid grid-cols-1 md:grid-cols-[1.2fr_1fr_.8fr_.8fr_0.9fr] gap-3 items-center min-h-[72px]">
              <div className="min-w-0">
                <p className="font-semibold text-slate-900 truncate">{row.requester_name || row.emp_id}</p>
                <p className="text-xs text-slate-500 mt-1 truncate">{row.asset_name} · {row.asset_category || 'Category not set'}</p>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-mono text-slate-600 truncate">{row.request_id}</p>
                <p className="text-xs text-slate-500 mt-1 truncate">{row.requester_branch || 'Branch not set'}</p>
              </div>
              <div className="space-y-1 min-w-0">
                {row.priority ? <Badge tone={priorityTone(row.priority)}>{row.priority}</Badge> : <span className="text-xs text-slate-400 uppercase tracking-wide">Not set yet</span>}
                <p className="text-xs text-slate-500 truncate">{row.priority_response_time || 'Waiting for support triage'}</p>
              </div>
              <div className="min-w-0">
                <Badge tone={stageTone(row.stage)} className="whitespace-nowrap">{row.stage || 'Unknown'}</Badge>
              </div>
              <div className="space-y-1 min-w-0">
                <Badge className="whitespace-nowrap">{row.status || 'Unknown'}</Badge>
                {row.escalation_triggered && row.escalation_role ? (
                  <p className="text-xs font-medium text-rose-600 truncate">Escalate to {row.escalation_role}</p>
                ) : null}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function DetailPanel({ row, user, mutations, onDelete, transferBranches = [] }) {
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [triagePriority, setTriagePriority] = useState('P3')
  const [triageSeverity, setTriageSeverity] = useState('MEDIUM')
  const [providedId, setProvidedId] = useState('')
  const [brokenId, setBrokenId] = useState('')
  const [resolveNotes, setResolveNotes] = useState('')
  const [repairCost, setRepairCost] = useState('0')
  const [disposable, setDisposable] = useState(false)
  const [tBranch, setTBranch] = useState('')
  const [rejectNotes, setRejectNotes] = useState('')
  const [aiRecommendation, setAiRecommendation] = useState(null)
  const [aiError, setAiError] = useState('')
  const [managerNotes, setManagerNotes] = useState('')
  const [transferConfirmOpen, setTransferConfirmOpen] = useState(false)

  const necessityMut = useMutation({
    mutationFn: (requestId) => apiFetch(`/requests/${requestId}/recommend-necessity`, { method: 'POST' }),
    onSuccess: (data) => {
      setAiError('')
      setAiRecommendation(data)
    },
    onError: (err) => {
      setAiRecommendation(null)
      setAiError(err?.message || 'Could not get recommendation.')
    },
  })

  const managerNotesMut = useMutation({
    mutationFn: ({ id, notes }) => apiFetch(`/requests/${id}/manager-notes`, { method: 'POST', body: JSON.stringify({ manager_notes: notes }) }),
    onSuccess: () => mutations.invalidate(),
  })

  const deleteMut = useMutation({
    mutationFn: (requestId) => apiFetch(`/requests/${encodeURIComponent(requestId)}`, { method: 'DELETE' }),
    onSuccess: () => {
      setDeleteConfirmOpen(false)
      mutations.invalidate()
      onDelete()
    },
  })

  useEffect(() => {
    setDeleteConfirmOpen(false)
    setTriagePriority('P3')
    setTriageSeverity('MEDIUM')
    setProvidedId('')
    setBrokenId('')
    setResolveNotes('')
    setRepairCost('0')
    setDisposable(false)
    setTBranch(transferBranches[0] || '')
    setRejectNotes('')
    setAiRecommendation(null)
    setAiError('')
    setManagerNotes('')
    setTransferConfirmOpen(false)
  }, [row?.request_id, transferBranches])

  if (!row) {
    return (
      <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50/80 p-8 text-center text-slate-500 text-sm motion-fade-up motion-delay-3">
        Select a request from the list to see complete details here.
      </div>
    )
  }

  const stage = row.stage
  const canDeleteRequest = stage === 'HR_VERIFICATION' && (
    user.role === R.ADMIN ||
    row.emp_id === user.employee_id ||
    ([R.MANAGER, R.HR, R.SUPPORT_TEAM].includes(user.role) && row.requester_branch === user.branch)
  )
  const autoUrgencyPreview = deriveUrgencyPreview({
    severity: triageSeverity,
    affectedUsers: 1,
    actionType: row.action_type || 'NEW',
    reason: row.reason,
    assetCategory: row.asset_category,
    assetName: row.asset_name,
  })
  const err = (m) => m.error?.message || m.error?.data?.message
  const detailRows = [
    ['Request ID', row.request_id],
    ['Asset name', row.asset_name || 'Not provided'],
    ['Category', row.asset_category || 'Not provided'],
    ['Requested by', row.requester_name || row.emp_id || 'Not available'],
    ['Requester role', row.requester_role || 'Not available'],
    ['Requester branch', row.requester_branch || 'Not available'],
    ['Employee ID', row.emp_id || 'Not available'],
    ['Stage', row.stage || 'Not available'],
    ['Status', row.status || 'Not available'],
    ['Request type', row.action_type || 'Not selected'],
    ['Priority', row.priority ? `${row.priority}${row.priority_response_time ? ` (${row.priority_response_time})` : ''}` : 'Waiting for support triage'],
    ['Severity', row.severity || 'Waiting for support triage'],
    ['Urgency', row.urgency || 'Waiting for support triage'],
    ['Urgency response target', row.urgency_response_time || 'Waiting for support triage'],
    ['HR verified', prettyBool(row.hr_verified)],
    ['Requested at', formatDate(row.req_date)],
    ['Manager notes', row.manager_notes || 'No notes'],
    ['Escalation', row.escalation_triggered && row.escalation_role ? `Overdue - escalate to ${row.escalation_role}` : 'Within current SLA'],
  ]

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-6 motion-fade-up motion-delay-3">
      <div className="flex flex-col gap-3 border-b border-slate-100 pb-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={stageTone(stage)}>{stage || 'Unknown stage'}</Badge>
          <Badge>{row.status || 'Unknown status'}</Badge>
          {row.action_type ? <Badge tone="cyan">Action: {row.action_type}</Badge> : null}
          {row.priority ? <Badge tone={priorityTone(row.priority)}>{row.priority}</Badge> : null}
          {row.severity ? <Badge tone={severityTone(row.severity)}>{row.severity}</Badge> : null}
          {row.urgency ? <Badge>{row.urgency} urgency</Badge> : null}
          {row.escalation_triggered && row.escalation_role ? <Badge tone="rose">Escalate to {row.escalation_role}</Badge> : null}
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Request details</p>
          <h3 className="text-2xl font-bold text-slate-900 mt-1">{row.asset_name}</h3>
          <p className="text-sm text-slate-600 mt-2 leading-6">{row.reason}</p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 overflow-hidden">
        <div className="grid grid-cols-1 sm:grid-cols-2">
          {detailRows.map(([label, value]) => (
            <div key={label} className="border-b border-slate-100 even:sm:border-l even:sm:border-l-slate-100 p-4 last:border-b-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
              <p className="mt-1 text-sm text-slate-800 break-words">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {canDeleteRequest ? (
        <>
          <div className="flex justify-end pt-4">
            <button
              type="button"
              className="rounded-xl bg-rose-600 text-white text-sm font-semibold px-4 py-2"
              disabled={deleteMut.isPending}
              onClick={() => setDeleteConfirmOpen(true)}
            >
              {deleteMut.isPending ? 'Deleting…' : 'Delete request'}
            </button>
          </div>
          <ConfirmDialog
            open={deleteConfirmOpen}
            title="Delete this request?"
            description="This removes the request before support review. This cannot be undone."
            confirmLabel="Delete request"
            busy={deleteMut.isPending}
            onCancel={() => !deleteMut.isPending && setDeleteConfirmOpen(false)}
            onConfirm={() => deleteMut.mutate(row.request_id)}
          />
        </>
      ) : null}
      {deleteMut.isError ? <p className="text-xs text-rose-600 mt-2">{err(deleteMut)}</p> : null}

      {stage === 'HR_VERIFICATION' && canNecessityRecommendation(user.role) ? (
        <div className="rounded-2xl border border-violet-200 bg-violet-50/60 px-4 py-4 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-violet-600" />
                AI necessity recommendation
              </p>
              <p className="text-xs text-slate-600 mt-0.5">
                Analyzes <strong>this request</strong> using the requester&apos;s active assignments, branch stock for the category, and recent request history. This is advisory only; HR/Admin should confirm the final decision.
              </p>
            </div>
            <button
              type="button"
              disabled={necessityMut.isPending}
              onClick={() => necessityMut.mutate(row.request_id)}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-700 text-white text-sm font-semibold px-4 py-2.5 disabled:opacity-50 shrink-0"
            >
              <Sparkles className="w-4 h-4" />
              {necessityMut.isPending ? 'Analyzing…' : 'Get recommendation'}
            </button>
          </div>
          {aiError ? <p className="text-xs text-rose-700 whitespace-pre-wrap break-words">{aiError}</p> : null}
          {aiRecommendation ? (
            <div className="rounded-xl border border-violet-100 bg-white p-3 text-sm space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`text-xs font-bold uppercase tracking-wide px-2 py-0.5 rounded-lg border ${
                    aiRecommendation.verdict === 'LIKELY_NEEDED'
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                      : aiRecommendation.verdict === 'LIKELY_REDUNDANT'
                        ? 'bg-rose-50 text-rose-800 border-rose-200'
                        : 'bg-amber-50 text-amber-900 border-amber-200'
                  }`}
                >
                  {String(aiRecommendation.verdict || '').replace(/_/g, ' ')}
                </span>
                <span className="text-xs text-slate-500">Confidence {aiRecommendation.confidence ?? '—'}%</span>
              </div>
              <div className="rounded-2xl bg-slate-50 p-3 border border-slate-200">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 mb-2">Suggested decision</p>
                <p className="text-sm font-semibold text-slate-900">
                  {aiRecommendation.verdict === 'LIKELY_NEEDED'
                    ? 'Recommend approval and fulfillment.'
                    : aiRecommendation.verdict === 'LIKELY_REDUNDANT'
                      ? 'Recommend rejection or further justification.'
                      : 'Recommend additional review before decision.'}
                </p>
              </div>
              <p className="text-slate-700 leading-relaxed">{aiRecommendation.summary}</p>
              {Array.isArray(aiRecommendation.factors) && aiRecommendation.factors.length > 0 ? (
                <ul className="list-disc pl-5 text-xs text-slate-600 space-y-0.5">
                  {aiRecommendation.factors.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              ) : null}
              {aiRecommendation.model_note ? (
                <p className="text-[11px] text-slate-400 italic">{aiRecommendation.model_note}</p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {canManagerReview(user.role) ? (
        <div className="space-y-3 border-t border-slate-100 pt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Manager notes</p>
          <textarea
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
            placeholder="Add internal notes for other managers..."
            value={managerNotes}
            onChange={(e) => setManagerNotes(e.target.value)}
            rows={3}
          />
          <button
            type="button"
            className="rounded-xl bg-blue-600 text-white text-sm font-medium px-4 py-2"
            onClick={() => managerNotesMut.mutate({ id: row.request_id, notes: managerNotes.trim() })}
            disabled={managerNotesMut.isPending}
          >
            {managerNotesMut.isPending ? 'Saving...' : 'Save notes'}
          </button>
          {managerNotesMut.isError ? <p className="text-xs text-rose-600">{err(managerNotesMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'HR_VERIFICATION' && canHrReview(user.role) ? (
        canAdminReview(user.role) ? (
          <div className="space-y-3 border-t border-slate-100 pt-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Admin override</p>
              <p className="mt-1 text-sm text-slate-600">Admins can bypass HR verification and approve or reject this request directly.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.admMut.mutate({ id: row.request_id, is_approved: true })}>Approve</button>
              <button type="button" className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.admMut.mutate({ id: row.request_id, is_approved: false })}>Reject</button>
              {mutations.admMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.admMut)}</p> : null}
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.hrMut.mutate({ id: row.request_id, is_needed: true })}>Mark needed</button>
            <button type="button" className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.hrMut.mutate({ id: row.request_id, is_needed: false })}>Not needed</button>
            {mutations.hrMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.hrMut)}</p> : null}
          </div>
        )
      ) : null}

      {stage === 'HELPDESK_TRIAGE' && canTriage(user.role) ? (
        <div className="space-y-4 border-t border-slate-100 pt-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Support triage</p>
            <p className="mt-1 text-sm text-slate-600">Support sets only severity and priority. Urgency is derived automatically from issue context and severity.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Priority</label>
              <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={triagePriority} onChange={(e) => setTriagePriority(e.target.value)}>
                {PRIORITY_OPTIONS.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <p className="text-xs text-slate-500">{PRIORITY_RESPONSE_TIME[triagePriority]} response target.</p>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Severity</label>
              <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={triageSeverity} onChange={(e) => setTriageSeverity(e.target.value)}>
                {SEVERITY_OPTIONS.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <p className="text-xs text-slate-500">{SEVERITY_HELP[triageSeverity]}</p>
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Auto urgency</span>
            <Badge tone={autoUrgencyPreview === 'HIGH' ? 'rose' : autoUrgencyPreview === 'MEDIUM' ? 'amber' : 'emerald'}>{autoUrgencyPreview}</Badge>
            <span className="text-sm text-slate-600">{URGENCY_RESPONSE_TIME[autoUrgencyPreview]} escalation limit from system rules.</span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-xl bg-indigo-600 text-white text-sm font-medium px-4 py-2"
              onClick={() => mutations.triageMut.mutate({
                id: row.request_id,
                priority: triagePriority,
                severity: triageSeverity,
              })}
            >
              Apply triage
            </button>
          </div>
          {mutations.triageMut.isError ? <p className="text-xs text-rose-600">{err(mutations.triageMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'MANAGER_APPROVAL' && canManagerReview(user.role) ? (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-5">
          <button type="button" className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.mgrMut.mutate({ id: row.request_id, is_approved: true })}>Approve</button>
          <button type="button" className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.mgrMut.mutate({ id: row.request_id, is_approved: false })}>Reject</button>
          {mutations.mgrMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.mgrMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'ADMIN_APPROVAL' && canAdminReview(user.role) ? (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-5">
          <button type="button" className="rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.admMut.mutate({ id: row.request_id, is_approved: true })}>Approve</button>
          <button type="button" className="rounded-xl bg-rose-600 text-white text-sm font-medium px-4 py-2" onClick={() => mutations.admMut.mutate({ id: row.request_id, is_approved: false })}>Reject</button>
          {mutations.admMut.isError ? <p className="text-xs text-rose-600 w-full">{err(mutations.admMut)}</p> : null}
        </div>
      ) : null}


      {canExecuteRequest(user.role) && (stage === 'READY' || row.status === 'APPROVED_FOR_SUPPORT' || row.status === 'READY') ? (
        <div className="space-y-3 border-t border-slate-100 pt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Execute fulfillment</p>
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Provided asset id (AST-123)" value={providedId} onChange={(e) => setProvidedId(e.target.value)} />
          {(row.action_type === 'REPLACE' || row.action_type === 'SERVICE') ? <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Broken / serviced asset id" value={brokenId} onChange={(e) => setBrokenId(e.target.value)} /> : null}
          <button
            type="button"
            className="rounded-xl bg-slate-900 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.execMut.mutate({ id: row.request_id, provided_asset_id: providedId || undefined, broken_asset_id: brokenId || undefined })}
          >
            Execute
          </button>
          {mutations.execMut.isError ? <p className="text-xs text-rose-600">{err(mutations.execMut)}</p> : null}
        </div>
      ) : null}

      {stage === 'IN_REPAIR' && canResolveService(user.role) ? (
        <div className="space-y-3 border-t border-slate-100 pt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Resolve service</p>
          <textarea className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Resolution notes" value={resolveNotes} onChange={(e) => setResolveNotes(e.target.value)} />
          <input className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" placeholder="Repair cost" value={repairCost} onChange={(e) => setRepairCost(e.target.value)} />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={disposable} onChange={(e) => setDisposable(e.target.checked)} />
            Asset is non-repairable
          </label>
          <button
            type="button"
            className="rounded-xl bg-teal-700 text-white text-sm font-medium px-4 py-2"
            onClick={() => mutations.resolveMut.mutate({ id: row.request_id, body: { resolution_notes: resolveNotes, repair_cost: parseFloat(repairCost) || 0, is_disposable: disposable } })}
          >
            Resolve service
          </button>
          {mutations.resolveMut.isError ? <p className="text-xs text-rose-600">{err(mutations.resolveMut)}</p> : null}
        </div>
      ) : null}

      {canTransferCrossBranch(user.role) ? (
        <div className="space-y-3 border-t border-slate-100 pt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Cross-branch transfer</p>
          <select className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" value={tBranch} onChange={(e) => setTBranch(e.target.value)}>
            <option value="">Select target branch</option>
            {transferBranches.map((branchName) => (
              <option key={branchName} value={branchName}>{branchName}</option>
            ))}
          </select>
          <button
            type="button"
            className="rounded-xl border border-slate-300 text-sm font-medium px-4 py-2"
            disabled={!tBranch}
            onClick={() => setTransferConfirmOpen(true)}
          >
            Request transfer
          </button>
          {!transferBranches.length ? <p className="text-xs text-slate-500">No active branches available.</p> : null}
          {mutations.transferMut.isError ? <p className="text-xs text-rose-600">{err(mutations.transferMut)}</p> : null}
        </div>
      ) : null}

      <ConfirmDialog
        open={transferConfirmOpen}
        title={tBranch ? `Request transfer to ${tBranch}?` : 'Request transfer?'}
        description="This will create a cross-branch transfer request and notify the target branch stakeholders."
        confirmLabel="Confirm transfer"
        variant="neutral"
        busy={mutations.transferMut.isPending}
        onCancel={() => !mutations.transferMut.isPending && setTransferConfirmOpen(false)}
        onConfirm={() => {
          mutations.transferMut.mutate(
            { id: row.request_id, body: { target_branch: tBranch } },
            { onSuccess: () => setTransferConfirmOpen(false) }
          )
        }}
      />
    </div>
  )
}

export default function Requests() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(10)
  const initialFilters = { priority: '', severity: '', urgency: '', request_type: '' }
  const [draftFilters, setDraftFilters] = useState(initialFilters)
  const [filters, setFilters] = useState(initialFilters)

  const formOptionsQuery = useQuery({
    queryKey: ['request-form-options'],
    queryFn: () => apiFetch('/requests/form-options'),
  })

  const transferBranchesQuery = useQuery({
    queryKey: ['request-transfer-target-branches'],
    queryFn: () => apiFetch('/requests/transfer-target-branches'),
    enabled: canTransferCrossBranch(user.role),
  })

  const { data = { items: [], total: 0, page: 1, per_page: perPage }, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['requests', filters, page, perPage],
    queryFn: () => {
      const params = new URLSearchParams()
      params.set('sort_by_status', 'true')
      params.set('page', String(page))
      params.set('per_page', String(perPage))
      if (filters.priority) params.set('priority', filters.priority)
      if (filters.severity) params.set('severity', filters.severity)
      if (filters.urgency) params.set('urgency', filters.urgency)
      if (filters.request_type) params.set('request_type', filters.request_type)
      const query = params.toString()
      return apiFetch(`/requests/${query ? `?${query}` : ''}`)
    },
  })

  useEffect(() => {
    if (selectedId && !data.items.some((row) => row.request_id === selectedId)) {
      setSelectedId(null)
      setDetailsOpen(false)
    }
  }, [data, selectedId])

  const selected = useMemo(() => data.items.find((r) => r.request_id === selectedId) ?? null, [data, selectedId])
  const invalidate = () => qc.invalidateQueries({ queryKey: ['requests'] })

  const hrMut = useMutation({ mutationFn: ({ id, is_needed }) => apiFetch(`/requests/${id}/review/hr`, { method: 'POST', body: JSON.stringify({ is_needed }) }), onSuccess: invalidate })
  const triageMut = useMutation({
    mutationFn: ({ id, priority, severity }) => apiFetch(`/requests/${id}/triage`, { method: 'POST', body: JSON.stringify({ priority, severity }) }),
    onSuccess: invalidate,
  })
  const mgrMut = useMutation({ mutationFn: ({ id, is_approved }) => apiFetch(`/requests/${id}/review/manager`, { method: 'POST', body: JSON.stringify({ is_approved }) }), onSuccess: invalidate })
  const admMut = useMutation({ mutationFn: ({ id, is_approved }) => apiFetch(`/requests/${id}/review/admin`, { method: 'POST', body: JSON.stringify({ is_approved }) }), onSuccess: invalidate })
  const execMut = useMutation({
    mutationFn: ({ id, provided_asset_id, broken_asset_id }) => {
      const q = new URLSearchParams()
      if (provided_asset_id) q.set('provided_asset_id', provided_asset_id)
      if (broken_asset_id) q.set('broken_asset_id', broken_asset_id)
      const qs = q.toString()
      return apiFetch(`/requests/${id}/execute${qs ? `?${qs}` : ''}`, { method: 'POST' })
    },
    onSuccess: invalidate,
  })
  const resolveMut = useMutation({ mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/resolve`, { method: 'POST', body: JSON.stringify(body) }), onSuccess: invalidate })
  const transferMut = useMutation({ mutationFn: ({ id, body }) => apiFetch(`/requests/${id}/transfer-request`, { method: 'POST', body: JSON.stringify(body) }), onSuccess: invalidate })
  const createMut = useMutation({ mutationFn: (body) => apiFetch('/requests/', { method: 'POST', body: JSON.stringify(body) }), onSuccess: () => invalidate() })

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 motion-fade-up">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Requests</h1>
          <p className="text-slate-600 text-sm mt-1">
            {user.role === R.ADMIN
              ? 'Request management and asset tracking. Use the Stock page for direct asset allocation.'
              : 'Guided request creation with known asset autofill, then full workflow review with priority-first visibility.'}
          </p>
        </div>
        <button type="button" onClick={() => { refetch(); formOptionsQuery.refetch() }} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
          <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {user.role !== R.ADMIN && (
        <>
          <NewRequestForm
            busy={createMut.isPending || formOptionsQuery.isLoading}
            options={formOptionsQuery.data}
            onCreate={(body) => {
              createMut.mutate(body, {
                onSuccess: (row) => {
                  if (row?.request_id) setSelectedId(row.request_id)
                },
              })
            }}
          />
          {formOptionsQuery.isError ? <p className="text-sm text-rose-600">{formOptionsQuery.error?.message}</p> : null}
          {createMut.isError ? <p className="text-sm text-rose-600">{createMut.error?.message}</p> : null}
        </>
      )}

      {isLoading ? (
        <div className="py-20 text-center text-slate-400 font-medium animate-pulse">Loading requests...</div>
      ) : isError ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-800 text-sm">{error?.message}</div>
      ) : (
        <div className="space-y-6">
          <RequestFilters
            draft={draftFilters}
            count={data.total}
            onChange={(key, value) => setDraftFilters((prev) => ({ ...prev, [key]: value }))}
            onApply={() => {
              setFilters(draftFilters)
              setPage(1)
            }}
            onClear={() => {
              setDraftFilters(initialFilters)
              setFilters(initialFilters)
              setPage(1)
            }}
          />
          <RequestList
            rows={data.items}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id)
              setDetailsOpen(true)
            }}
          />
          <div className="flex flex-col gap-3 justify-between rounded-3xl border border-slate-200 bg-white p-4 text-sm text-slate-600 sm:flex-row">
            <div>
              Showing {(page - 1) * perPage + 1} to {Math.min(page * perPage, data.total)} of {data.total} requests
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50"
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= Math.max(1, Math.ceil(data.total / perPage))}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50"
                onClick={() => setPage((prev) => prev + 1)}
              >
                Next
              </button>
              <select
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
                value={perPage}
                onChange={(e) => {
                  setPerPage(Number(e.target.value) || 10)
                  setPage(1)
                }}
              >
                {[5, 10, 20, 50].map((size) => (
                  <option key={size} value={size}>{size} per page</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}

      {detailsOpen && selected ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/70 backdrop-blur-sm" onClick={() => setDetailsOpen(false)}>
          <div className="relative w-full max-w-6xl max-h-[90vh] overflow-auto rounded-3xl bg-white shadow-2xl border border-slate-200" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className="absolute right-4 top-4 inline-flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200"
              onClick={() => setDetailsOpen(false)}
              aria-label="Close request details"
            >
              ×
            </button>
            <div className="p-6">
              <DetailPanel row={selected} user={user} mutations={{ hrMut, triageMut, mgrMut, admMut, execMut, resolveMut, transferMut, invalidate }} onDelete={() => setDetailsOpen(false)} transferBranches={transferBranchesQuery.data || []} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
