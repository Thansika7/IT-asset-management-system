export function normalizeOptionItem(item) {
  if (item == null) return null

  if (typeof item === 'string' || typeof item === 'number') {
    const value = String(item)
    return { id: value, name: value, raw: item }
  }

  if (typeof item !== 'object') return null

  const id =
    item.id ??
    item.value ??
    item.attribute_id ??
    item.asset_id ??
    item.instance_id ??
    item.request_id ??
    item.branch_id ??
    item.category_id ??
    item.sub_category_id ??
    item.employee_id ??
    item.organization_id ??
    null

  const name =
    item.name ??
    item.label ??
    item.attribute_name ??
    item.asset_name ??
    item.request_name ??
    item.title ??
    item.branch_name ??
    item.category_name ??
    item.sub_category_name ??
    item.organization_name ??
    item.employee_name ??
    item.full_name ??
    null

  if (id == null && name == null) return null

  const normalizedId = String(id ?? name)
  const normalizedName = String(name ?? id)
  return { id: normalizedId, name: normalizedName, raw: item }
}

export function normalizeOptions(options) {
  if (!Array.isArray(options)) return []
  const out = []
  const seen = new Set()

  for (const item of options) {
    const normalized = normalizeOptionItem(item)
    if (!normalized) continue
    if (seen.has(normalized.id)) continue
    seen.add(normalized.id)
    out.push(normalized)
  }

  return out
}
