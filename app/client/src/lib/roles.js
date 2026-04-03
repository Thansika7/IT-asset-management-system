/** Matches backend `EmployeeRole` string values */
export const R = {
  ADMIN: 'admin',
  MANAGER: 'manager',
  HR: 'hr',
  SUPPORT_TEAM: 'support_team',
  EMPLOYEE: 'employee',
}

export const ROLE_LABEL = {
  [R.ADMIN]: 'Administrator',
  [R.MANAGER]: 'Manager',
  [R.HR]: 'HR',
  [R.SUPPORT_TEAM]: 'Support',
  [R.EMPLOYEE]: 'Employee',
}

export function normalizeRole(value) {
  if (!value) return R.EMPLOYEE
  return String(value).toLowerCase()
}

export function labelForRole(role) {
  return ROLE_LABEL[normalizeRole(role)] || role
}

/** Navigation and route guards */
export const NAV = {
  dashboard: () => true,
  myAssets: () => true,
  requests: () => true,
  tracking: () => true,
  employees: (r) => [R.ADMIN, R.HR, R.MANAGER].includes(r),
  /** View kits for registration / allocation planning */
  onboardingKits: (r) => [R.ADMIN, R.MANAGER, R.HR].includes(r),
  stock: (r) => [R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM].includes(r),
  finance: (r) => [R.ADMIN, R.MANAGER].includes(r),
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
