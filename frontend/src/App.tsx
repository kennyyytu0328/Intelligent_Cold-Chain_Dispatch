import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from '@/stores/authStore'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import DepotsPage from '@/pages/DepotsPage'
import VehiclesPage from '@/pages/VehiclesPage'
import ShipmentsPage from '@/pages/ShipmentsPage'
import ImportPage from '@/pages/ImportPage'
import OptimizationPage from '@/pages/OptimizationPage'
import MapPage from '@/pages/MapPage'
import MainLayout from '@/components/Layout/MainLayout'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function App() {
  return (
    <>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 3000,
          style: {
            background: 'hsl(var(--card))',
            color: 'hsl(var(--card-foreground))',
            border: '1px solid hsl(var(--border))',
          },
        }}
      />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="depots" element={<DepotsPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
          <Route path="shipments" element={<ShipmentsPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="optimization" element={<OptimizationPage />} />
          <Route path="map" element={<MapPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}

export default App
