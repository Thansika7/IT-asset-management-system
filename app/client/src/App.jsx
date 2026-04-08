import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { ProtectedShell, RoleGate } from './components/AppShell'
import { R } from './lib/roles'
import { useAuth } from './context/AuthContext'

import Login from './pages/Login'
import ForgotPassword from './pages/ForgotPassword'
import Dashboard from './pages/Dashboard'
import Tracking from './pages/Tracking'
import Employees from './pages/Employees'
import Requests from './pages/Requests'
import Stock from './pages/Stock'
import Finance from './pages/Finance'
import MyAssets from './pages/MyAssets'
import OnboardingKits from './pages/OnboardingKits'
import CMDB from './pages/CMDB'
import AssetUsage from './pages/AssetUsage'
import ChangePassword from './pages/ChangePassword'
import Organizations from './pages/Organizations'
import MainLayout from './layouts/MainLayout'

const APP_ROLES = [R.SUPER_ADMIN, R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM, R.EMPLOYEE]
const BUSINESS_ROLES = [R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM, R.EMPLOYEE]

function DefaultRoute() {
  const { user } = useAuth()
  if (user?.role === R.SUPER_ADMIN) {
    return <Navigate to="/organizations" replace />
  }
  return <Dashboard />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route element={<ProtectedShell anyOfRoles={APP_ROLES} />}>
        <Route element={<MainLayout />}>
          <Route index element={<DefaultRoute />} />
          <Route path="organizations" element={<RoleGate roles={[R.SUPER_ADMIN, R.ORG_ADMIN]}><Organizations /></RoleGate>} />
          <Route path="my-assets" element={<RoleGate roles={BUSINESS_ROLES}><MyAssets /></RoleGate>} />
          <Route path="requests" element={<RoleGate roles={BUSINESS_ROLES}><Requests /></RoleGate>} />
          <Route path="stock" element={<RoleGate roles={[R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM]}><Stock /></RoleGate>} />
          <Route
            path="asset-usage"
            element={
              <RoleGate roles={[R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM]}>
                <AssetUsage />
              </RoleGate>
            }
          />
          <Route path="tracking" element={<RoleGate roles={BUSINESS_ROLES}><Tracking /></RoleGate>} />
          <Route
            path="finance"
            element={
              <RoleGate
                allow={(u) =>
                  [R.ADMIN, R.MANAGER].includes(u.role) ||
                  Boolean(u.permissions?.can_view_finance || u.permissions?.can_manage_finance)
                }
              >
                <Finance />
              </RoleGate>
            }
          />
          <Route path="employees" element={<RoleGate roles={[R.ADMIN, R.HR, R.MANAGER]}><Employees /></RoleGate>} />
          <Route
            path="onboarding-kits"
            element={
              <RoleGate roles={[R.ADMIN, R.MANAGER, R.HR]}>
                <OnboardingKits />
              </RoleGate>
            }
          />
          <Route
            path="cmdb"
            element={
              <RoleGate roles={[R.ADMIN, R.MANAGER, R.HR, R.SUPPORT_TEAM]}>
                <CMDB />
              </RoleGate>
            }
          />
          <Route path="change-password" element={<ChangePassword />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
