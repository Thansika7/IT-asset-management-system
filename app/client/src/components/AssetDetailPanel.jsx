import React from 'react'

function DetailItem({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-medium text-slate-900 break-words">{value || '-'}</p>
    </div>
  )
}

function formatCurrency(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export default function AssetDetailPanel({ asset, title = 'Asset Details', subtitle = 'Click any asset to inspect full details.' }) {
  if (!asset) {
    return (
      <aside className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/80 p-8 text-center text-slate-500 text-sm">
        {subtitle}
      </aside>
    )
  }

  return (
    <aside className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-6">
      <div className="border-b border-slate-100 pb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{title}</p>
        <h2 className="mt-2 text-xl font-bold text-slate-900">{asset.name}</h2>
        <p className="mt-1 text-sm text-slate-500">{asset.asset_id}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <DetailItem label="Category" value={asset.category} />
        <DetailItem label="Sub Category" value={asset.sub_category} />
        <DetailItem label="Brand" value={asset.brand} />
        <DetailItem label="Branch" value={asset.branch} />
        <DetailItem label="Status" value={asset.status} />
        <DetailItem label="Health Score" value={asset.health_score ? `${asset.health_score}/100` : '0/100'} />
        <DetailItem label="Health Class" value={asset.health_classification || '-'} />
        <DetailItem label="Total Quantity" value={asset.total_quantity} />
        <DetailItem label="Used / Available" value={`${asset.used} / ${asset.unused}`} />
        <DetailItem label="Low Stock" value={asset.low_stock ? `Yes (threshold ${asset.low_stock_threshold})` : 'No'} />
        <DetailItem label="Purchased Date" value={asset.purchased_date} />
        <DetailItem label="Asset Age" value={asset.asset_age_days ? `${asset.asset_age_days} days` : '0 days'} />
        <DetailItem label="Useful Life" value={asset.useful_life_years ? `${asset.useful_life_years} years` : '-'} />
        <DetailItem label="Buying Cost" value={formatCurrency(asset.purchase_cost)} />
        <DetailItem label="Reselling Value" value={formatCurrency(asset.reselling_value ?? asset.salvage_value)} />
        <DetailItem label="Maintenance Cost" value={formatCurrency(asset.maintenance_cost)} />
        <DetailItem label="Service / Repair Cost" value={formatCurrency(asset.repair_cost)} />
        <DetailItem label="License Cost" value={formatCurrency(asset.sub_license_cost)} />
        <DetailItem label="Annual Depreciation" value={formatCurrency(asset.annual_depreciation)} />
        <DetailItem label="Accumulated Depreciation" value={formatCurrency(asset.accumulated_depreciation)} />
        <DetailItem label="Book Value" value={formatCurrency(asset.book_value)} />
        <DetailItem label="Total Cost of Ownership" value={formatCurrency(asset.total_cost_of_ownership)} />
        <DetailItem label="Vendor" value={asset.vendor_name} />
        <DetailItem label="Vendor Contact" value={asset.vendor_contact} />
        <DetailItem label="Invoice Number" value={asset.invoice_number} />
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">Recommendation</p>
        <p className={`mt-2 inline-flex rounded-lg px-2 py-1 text-xs font-semibold uppercase tracking-wide ${asset.recommendation === 'REPLACE' ? 'bg-rose-50 text-rose-700 border border-rose-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'}`}>
          {asset.recommendation}
        </p>
        <p className="mt-3 text-sm text-slate-700">{asset.recommendation_reason}</p>
      </div>
    </aside>
  )
}
