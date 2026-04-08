/** Matches backend `EmployeeRole` string values */
export const R = {
  SUPER_ADMIN: 'super_admin',
  ADMIN: 'org_admin',
  ORG_ADMIN: 'org_admin',
  MANAGER: 'manager',
  HR: 'hr',
  SUPPORT_TEAM: 'support_team',
  EMPLOYEE: 'employee',
}

export const ROLE_LABEL = {
  [R.SUPER_ADMIN]: 'Super Admin',
  [R.ORG_ADMIN]: 'Org Admin',
  [R.MANAGER]: 'Manager',
  [R.HR]: 'HR',
  [R.SUPPORT_TEAM]: 'Support',
  [R.EMPLOYEE]: 'Employee',
}

export function normalizeRole(value) {
  if (!value) return R.EMPLOYEE
  const normalized = String(value).toLowerCase()
  if (normalized === 'admin') return R.ORG_ADMIN
  return normalized
}

export function labelForRole(role) {
  return ROLE_LABEL[normalizeRole(role)] || role
}

/** Navigation and route guards */
export const NAV = {
  dashboard: (r) => r !== R.SUPER_ADMIN,
  myAssets: (r) => r !== R.SUPER_ADMIN,
  requests: (r) => r !== R.SUPER_ADMIN,
  tracking: (r) => r !== R.SUPER_ADMIN,
  organizations: (r) => [R.SUPER_ADMIN, R.ORG_ADMIN].includes(r),
  employees: (r, p) =>
    [R.ADMIN, R.ORG_ADMIN, R.HR, R.MANAGER].includes(r) ||
    Boolean(p?.can_manage_users || p?.can_manage_permissions),
  /** View kits for registration / allocation planning */
  onboardingKits: (r) => [R.ADMIN, R.MANAGER, R.HR].includes(r),
  stock: (r) => [R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM].includes(r),
  /** Allocation / repair / movement metrics — GET /assets/usage/* */
  assetUsage: (r) => [R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM].includes(r),
  finance: (r, p) =>
    [R.ADMIN, R.MANAGER].includes(r) ||
    Boolean(p?.can_view_finance || p?.can_manage_finance),
  /** CMDB items & relationships — matches backend GET /cmdb/* */
  cmdb: (r) => [R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM].includes(r),
}

export function canManageStockWrites(r) {
  return [R.ADMIN, R.SUPPORT_TEAM].includes(r)
}

/** Manual allocate / return — backend: admin only */
export function canManualStockOverride(r) {
  return r === R.ADMIN
}

/** Deactivate employee + recover hardware — backend: HR + admin */
export function canDeactivateEmployees(r) {
  return [R.ADMIN, R.HR].includes(r)
}

export function canManageOnboardingKits(r) {
  return [R.ADMIN, R.MANAGER, R.HR].includes(r)
}

export function canRegisterEmployees(r) {
  return [R.ADMIN, R.HR].includes(r)
}

export function canTriage(r) {
  return [R.ADMIN, R.SUPPORT_TEAM].includes(r)
}

export function canHrReview(r) {
  return [R.ADMIN, R.HR].includes(r)
}

/** Gemini necessity recommendation for a specific request — backend POST /requests/:id/recommend-necessity */
export function canNecessityRecommendation(r) {
  return [R.ADMIN, R.ORG_ADMIN, R.HR].includes(r)
}

export function canManagerReview(r) {
  return [R.ADMIN, R.MANAGER].includes(r)
}

export function canAdminReview(r) {
  return r === R.ADMIN
}

export function canExecuteRequest(r) {
  return [R.ADMIN, R.SUPPORT_TEAM].includes(r)
}

export function canResolveService(r) {
  return [R.ADMIN, R.SUPPORT_TEAM].includes(r)
}

export function canTransferCrossBranch(r) {
  return r === R.MANAGER
}

export function canManagePermissions(r, p) {
  return [R.ADMIN, R.ORG_ADMIN].includes(r) || Boolean(p?.can_manage_permissions)
}
