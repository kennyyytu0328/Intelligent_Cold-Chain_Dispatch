import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import {
  Truck,
  Package,
  Clock,
  CheckCircle,
  Thermometer,
  AlertTriangle,
  TrendingUp,
  Activity,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { vehicleAPI, shipmentAPI } from '@/services/api'
import { cn } from '@/lib/utils'

type StatVariant = 'default' | 'success' | 'warning' | 'cold' | 'primary'

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ReactNode
  description?: string
  variant?: StatVariant
  trend?: {
    value: number
    label: string
  }
}

const variantStyles: Record<StatVariant, string> = {
  default: 'border-l-4 border-l-muted',
  success: 'border-l-4 border-l-success',
  warning: 'border-l-4 border-l-warning',
  cold: 'border-l-4 border-l-cold',
  primary: 'border-l-4 border-l-primary',
}

const iconVariantStyles: Record<StatVariant, string> = {
  default: 'text-muted-foreground',
  success: 'text-success',
  warning: 'text-warning',
  cold: 'text-cold',
  primary: 'text-primary',
}

function StatCard({
  title,
  value,
  icon,
  description,
  variant = 'default',
  trend,
}: StatCardProps) {
  return (
    <Card className={cn('transition-shadow hover:shadow-md cursor-pointer', variantStyles[variant])}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-gray-700">
          {title}
        </CardTitle>
        <div className={cn('p-2 rounded-lg bg-muted/50', iconVariantStyles[variant])}>
          {icon}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold tracking-tight">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        )}
        {trend && (
          <div className="flex items-center gap-1 mt-2">
            <TrendingUp
              className={cn(
                'h-3 w-3',
                trend.value >= 0 ? 'text-success' : 'text-destructive'
              )}
            />
            <span
              className={cn(
                'text-xs font-medium',
                trend.value >= 0 ? 'text-success' : 'text-destructive'
              )}
            >
              {trend.value >= 0 ? '+' : ''}
              {trend.value}%
            </span>
            <span className="text-xs text-muted-foreground">{trend.label}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { t } = useTranslation()

  const { data: vehicles = [] } = useQuery({
    queryKey: ['vehicles'],
    queryFn: vehicleAPI.getAll,
    retry: false,
  })

  const { data: shipments = [] } = useQuery({
    queryKey: ['shipments'],
    queryFn: shipmentAPI.getAll,
    retry: false,
  })

  const shipmentsArray = Array.isArray(shipments) ? shipments : []
  const vehiclesArray = Array.isArray(vehicles) ? vehicles : []
  const pendingShipments = shipmentsArray.filter((s) => s.status === 'pending').length
  const deliveredToday = shipmentsArray.filter((s) => s.status === 'delivered').length
  const activeVehicles = vehiclesArray.filter((v) => v.status === 'active').length

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight">
          {t('dashboard.title')}
        </h1>
        <p className="text-Gray-600">
          Monitor your cold-chain fleet and shipments in real-time
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title={t('dashboard.totalVehicles')}
          value={vehiclesArray.length}
          icon={<Truck className="h-4 w-4" />}
          description={`${activeVehicles} active`}
          variant="primary"
        />
        <StatCard
          title={t('dashboard.totalShipments')}
          value={shipmentsArray.length}
          icon={<Package className="h-4 w-4" />}
          variant="cold"
        />
        <StatCard
          title={t('dashboard.pendingShipments')}
          value={pendingShipments}
          icon={<Clock className="h-4 w-4" />}
          description="Awaiting dispatch"
          variant={pendingShipments > 10 ? 'warning' : 'default'}
        />
        <StatCard
          title={t('dashboard.completedToday')}
          value={deliveredToday}
          icon={<CheckCircle className="h-4 w-4" />}
          variant="success"
          trend={{ value: 12, label: 'vs yesterday' }}
        />
      </div>

      {/* Secondary Stats & Activity */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Temperature Status */}
        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">
                Temperature Status
              </CardTitle>
              <Thermometer className="h-4 w-4 text-cold" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-success" />
                  <span className="text-sm">Normal Range</span>
                </div>
                <span className="text-sm font-medium">{vehiclesArray.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-warning" />
                  <span className="text-sm">Warning</span>
                </div>
                <span className="text-sm font-medium">0</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-destructive" />
                  <span className="text-sm">Critical</span>
                </div>
                <span className="text-sm font-medium">0</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">
                {t('dashboard.recentActivity')}
              </CardTitle>
              <Activity className="h-4 w-4 text-primary" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {shipmentsArray.length > 0 ? (
                shipmentsArray.slice(0, 3).map((shipment, index) => (
                  <div
                    key={shipment.id || index}
                    className="flex items-center gap-2 text-sm"
                  >
                    <div
                      className={cn(
                        'h-1.5 w-1.5 rounded-full',
                        shipment.status === 'delivered'
                          ? 'bg-success'
                          : shipment.status === 'in_transit'
                          ? 'bg-primary'
                          : 'bg-muted-foreground'
                      )}
                    />
                    <span className="truncate flex-1">
                      Shipment #{shipment.id?.slice(-6) || index + 1}
                    </span>
                    <span className="text-xs text-muted-foreground capitalize">
                      {shipment.status?.replace('_', ' ')}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  {t('common.none')}
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* System Status */}
        <Card className="cursor-pointer hover:shadow-md transition-shadow">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">
                {t('dashboard.systemStatus')}
              </CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm">API Server</span>
                <div className="flex items-center gap-1.5">
                  <div className="h-2 w-2 rounded-full bg-success animate-pulse" />
                  <span className="text-xs text-success font-medium">Online</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Optimization Engine</span>
                <div className="flex items-center gap-1.5">
                  <div className="h-2 w-2 rounded-full bg-success animate-pulse" />
                  <span className="text-xs text-success font-medium">Ready</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Cold-Chain Monitor</span>
                <div className="flex items-center gap-1.5">
                  <div className="h-2 w-2 rounded-full bg-success animate-pulse" />
                  <span className="text-xs text-success font-medium">Active</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
