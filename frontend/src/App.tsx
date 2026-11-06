import { Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import {
  ProtectedRoute,
  PublicOnlyRoute,
} from '@/components/layout/ProtectedRoute'
import { DashboardPage } from '@/pages/DashboardPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { LoginPage } from '@/pages/LoginPage'
import { AccountPage } from '@/pages/AccountPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ForgotPasswordPage, ResetPasswordPage } from '@/pages/PasswordResetPages'
import { PredictPage } from '@/pages/PredictPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { ResultPage } from '@/pages/ResultPage'

function App() {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      </Route>

      {/* Reachable signed in or out: the link arrives by email. */}
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="/predict" element={<PredictPage />} />
          <Route path="/predictions/:id" element={<ResultPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/account" element={<AccountPage />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
