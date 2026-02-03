import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Play, Loader2, Map, Warehouse, Navigation, Calendar, Clock, AlertTriangle, Thermometer, PackageX, PackageCheck, Info, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useOptimizationStore } from '@/stores/optimizationStore'
import { optimizationAPI, depotAPI, routesAPI, shipmentAPI, OptimizationParams } from '@/services/api'

export default function OptimizationPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { currentResult, violations, isOptimizing, setResult, setViolations, setOptimizing, updateProgress } =
    useOptimizationStore()

  // Get today's date in YYYY-MM-DD format
  const today = new Date().toISOString().split('T')[0]

  const [params, setParams] = useState<OptimizationParams>({
    plan_date: today,
    planned_departure_time: '06:00',
    depot_lat: 25.033,
    depot_lon: 121.5654,
    ambient_temp: 30,
    initial_cargo_temp: -5,
    max_iterations: 200,
  })

  const [depotInputMode, setDepotInputMode] = useState<'select' | 'manual'>('select')
  const [selectedDepotId, setSelectedDepotId] = useState<string>('')

  // Fetch depots
  const { data: depotsResponse, isLoading: isLoadingDepots } = useQuery({
    queryKey: ['depots'],
    queryFn: async () => {
      const data = await depotAPI.getAll()
      return data
    },
  })

  // Fetch shipments to check pending count - always refetch to get latest status
  const { data: shipments = [], isLoading: isLoadingShipments, refetch: refetchShipments } = useQuery({
    queryKey: ['shipments'],
    queryFn: shipmentAPI.getAll,
    staleTime: 0, // Always consider data stale
    refetchOnMount: 'always', // Refetch when component mounts
    refetchOnWindowFocus: true, // Refetch when window regains focus
  })

  // Refetch shipments when page becomes visible (e.g., after navigating back)
  useEffect(() => {
    refetchShipments()
  }, [refetchShipments])

  const shipmentsArray = Array.isArray(shipments) ? shipments : []
  // Compare status case-insensitively (API may return 'PENDING' or 'pending')
  const pendingShipments = shipmentsArray.filter((s) => s.status?.toLowerCase() === 'pending')
  const pendingCount = pendingShipments.length
  const totalShipments = shipmentsArray.length

  const depots = depotsResponse?.depots || []
  const activeDepots = depots.filter((d) => d.is_active)

  // Auto-select first depot if only one exists
  useEffect(() => {
    if (depotInputMode === 'select' && activeDepots.length === 1 && !selectedDepotId) {
      handleDepotSelect(activeDepots[0].id)
    }
  }, [activeDepots, depotInputMode, selectedDepotId])

  // Poll for optimization status
  useEffect(() => {
    let intervalId: number | null = null

    if (isOptimizing && currentResult?.taskId) {
      intervalId = setInterval(async () => {
        try {
          const status = await optimizationAPI.getStatus(currentResult.taskId, params.max_iterations)

          if (status.status === 'completed') {
            const result = await optimizationAPI.getResult(currentResult.taskId)

            // Fetch actual route data for map visualization
            let routeData = null
            try {
              routeData = await routesAPI.getForMap(params.plan_date, currentResult.taskId)
            } catch (e) {
              console.error('Failed to fetch route data:', e)
            }

            // Fetch violation details
            let violationData = null
            try {
              violationData = await optimizationAPI.getViolations(currentResult.taskId)
              setViolations(violationData)
            } catch (e) {
              console.error('Failed to fetch violations:', e)
            }

            // Map route data to store format
            const mappedRoutes = routeData?.routes.map((r) => ({
              vehicleId: r.vehicleId,
              licensePlate: r.licensePlate,
              color: '',  // Will be assigned by MapPage
              totalDistance: r.totalDistance,
              totalTime: r.totalTime,
              stops: r.stops.map(s => ({
                sequence: s.sequence,
                shipmentId: s.shipmentId,
                customerName: s.customerName,
                address: s.address,
                lat: s.lat,
                lon: s.lon,
                arrivalTime: s.arrivalTime,
                departureTime: s.departureTime,
                temperature: s.temperature,
                tempLimit: s.tempLimit,
                feasible: s.feasible,
              })),
            })) || []

            // Determine feasibility: feasible if no unassigned shipments and no temp violations
            const isFeasible = result.shipmentsUnassigned === 0 &&
              (!violationData || violationData.summary.total_temp_violations === 0)

            setResult({
              ...currentResult,
              status: 'completed',
              progress: 100,
              totalDistance: result.totalDistance,
              totalTime: result.totalTime,
              routes: mappedRoutes,
              feasible: isFeasible,
              depot: routeData?.depot || { lat: params.depot_lat, lon: params.depot_lon },
            })
            setOptimizing(false)
            toast.success(t('optimization.optimizationComplete'))
          } else if (status.status === 'failed') {
            setResult({
              ...currentResult,
              status: 'failed',
              progress: 0,
              message: status.error,
            })
            setOptimizing(false)
            toast.error(t('optimization.optimizationFailed'))
          } else {
            updateProgress(status.progress || 0)
          }
        } catch (error) {
          console.error('Failed to get optimization status:', error)
        }
      }, 2000)
    }

    return () => {
      if (intervalId) clearInterval(intervalId)
    }
  }, [isOptimizing, currentResult?.taskId])

  const handleStartOptimization = async () => {
    // Validate depot selection
    if (depotInputMode === 'select' && !selectedDepotId) {
      toast.error(t('optimization.pleaseSelectDepot'))
      return
    }

    // Check if there are pending shipments
    if (pendingCount === 0) {
      if (totalShipments === 0) {
        toast.error(t('optimization.noShipmentsFound'))
      } else {
        toast.error(t('optimization.allShipmentsAssigned'))
      }
      return
    }

    try {
      setOptimizing(true)
      setViolations(null)  // Clear previous violations
      const { task_id } = await optimizationAPI.start(params)
      setResult({
        taskId: task_id,
        status: 'running',
        progress: 0,
        routes: [],
        totalDistance: 0,
        totalTime: 0,
        feasible: false,
      })
    } catch (error) {
      toast.error(t('optimization.optimizationFailed'))
      setOptimizing(false)
    }
  }

  const handleViewOnMap = () => {
    navigate('/map')
  }

  const handleDepotSelect = (depotId: string) => {
    setSelectedDepotId(depotId)
    const depot = depots.find((d) => d.id === depotId)
    if (depot) {
      setParams({
        ...params,
        depot_lat: Number(depot.latitude),
        depot_lon: Number(depot.longitude),
      })
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('optimization.title')}</h1>
      </div>

      {/* Shipment Status Warning */}
      {!isLoadingShipments && pendingCount === 0 && (
        <Card className="border-warning bg-warning/5">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-3">
              {totalShipments === 0 ? (
                <PackageX className="h-6 w-6 text-warning" />
              ) : (
                <PackageCheck className="h-6 w-6 text-warning" />
              )}
              <div>
                <CardTitle className="text-warning">
                  {t('optimization.noPendingShipments')}
                </CardTitle>
                <CardDescription className="mt-1">
                  {totalShipments === 0
                    ? t('optimization.noShipmentsFound')
                    : t('optimization.allShipmentsAssigned')}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                onClick={() => navigate('/shipments')}
                className="border-warning text-warning hover:bg-warning hover:text-white"
              >
                {t('optimization.goToShipments')}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => refetchShipments()}
                disabled={isLoadingShipments}
                className="text-muted-foreground"
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${isLoadingShipments ? 'animate-spin' : ''}`} />
                {t('common.refresh')}
              </Button>
              {totalShipments > 0 && (
                <span className="text-sm text-muted-foreground">
                  {totalShipments} {t('shipments.title').toLowerCase()} ({shipmentsArray.filter(s => s.status?.toLowerCase() === 'assigned').length} assigned)
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Pending Shipments Info */}
      {!isLoadingShipments && pendingCount > 0 && (
        <Card className="border-success bg-success/5">
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Info className="h-5 w-5 text-success" />
                <span className="text-sm text-success font-medium">
                  {t('optimization.pendingCount', { count: pendingCount })}
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => refetchShipments()}
                disabled={isLoadingShipments}
                className="text-muted-foreground"
              >
                <RefreshCw className={`h-4 w-4 ${isLoadingShipments ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Optimization Parameters */}
        <Card>
          <CardHeader>
            <CardTitle>{t('optimization.parameters')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Plan Date and Departure Time */}
            <div className="grid grid-cols-2 gap-4 p-3 bg-muted rounded-lg">
              <div className="space-y-2">
                <Label htmlFor="plan_date" className="flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  {t('optimization.planDate', 'Plan Date')}
                </Label>
                <Input
                  id="plan_date"
                  type="date"
                  value={params.plan_date}
                  onChange={(e) => setParams({ ...params, plan_date: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="departure_time" className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  {t('optimization.departureTime', 'Departure Time')}
                </Label>
                <Input
                  id="departure_time"
                  type="time"
                  value={params.planned_departure_time}
                  onChange={(e) => setParams({ ...params, planned_departure_time: e.target.value })}
                />
              </div>
            </div>

            {/* Depot Selection Mode Toggle */}
            <div className="flex items-center gap-4 p-3 bg-muted rounded-lg">
              <Label className="text-sm font-medium">{t('optimization.depotLocation')}:</Label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={depotInputMode === 'select' ? 'default' : 'outline'}
                  onClick={() => setDepotInputMode('select')}
                >
                  <Warehouse className="mr-2 h-4 w-4" />
                  {t('optimization.selectDepotMode')}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={depotInputMode === 'manual' ? 'default' : 'outline'}
                  onClick={() => setDepotInputMode('manual')}
                >
                  <Navigation className="mr-2 h-4 w-4" />
                  {t('optimization.manualInputMode')}
                </Button>
              </div>
            </div>

            {/* Depot Selector Mode */}
            {depotInputMode === 'select' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="depot-select">{t('optimization.selectDepotRequired')}</Label>
                  <Select value={selectedDepotId} onValueChange={handleDepotSelect}>
                    <SelectTrigger id="depot-select">
                      <SelectValue placeholder={t('optimization.chooseDepot')} />
                    </SelectTrigger>
                    <SelectContent>
                      {isLoadingDepots ? (
                        <div className="flex items-center justify-center p-4">
                          <Loader2 className="h-4 w-4 animate-spin" />
                        </div>
                      ) : activeDepots.length === 0 ? (
                        <div className="p-4 text-sm text-muted-foreground text-center">
                          {t('optimization.noDepotsFound')}
                        </div>
                      ) : (
                        activeDepots.map((depot) => (
                          <SelectItem key={depot.id} value={depot.id}>
                            <div className="flex flex-col">
                              <span className="font-medium">{depot.name}</span>
                              {depot.code && (
                                <span className="text-xs text-muted-foreground">
                                  {depot.code} • {Number(depot.latitude).toFixed(4)}, {Number(depot.longitude).toFixed(4)}
                                </span>
                              )}
                            </div>
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  {selectedDepotId && (
                    <p className="text-xs text-muted-foreground">
                      {t('optimization.coordinates')}: {params.depot_lat.toFixed(4)}, {params.depot_lon.toFixed(4)}
                    </p>
                  )}
                </div>
              </>
            )}

            {/* Manual Coordinates Mode */}
            {depotInputMode === 'manual' && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="depot_lat">{t('optimization.depotLat')}</Label>
                  <Input
                    id="depot_lat"
                    type="number"
                    step="0.0001"
                    value={params.depot_lat}
                    onChange={(e) => setParams({ ...params, depot_lat: Number(e.target.value) })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="depot_lon">{t('optimization.depotLon')}</Label>
                  <Input
                    id="depot_lon"
                    type="number"
                    step="0.0001"
                    value={params.depot_lon}
                    onChange={(e) => setParams({ ...params, depot_lon: Number(e.target.value) })}
                  />
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="ambient_temp">{t('optimization.ambientTemp')}</Label>
                <Input
                  id="ambient_temp"
                  type="number"
                  value={params.ambient_temp}
                  onChange={(e) => setParams({ ...params, ambient_temp: Number(e.target.value) })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="initial_cargo_temp">{t('optimization.initialTemp')}</Label>
                <Input
                  id="initial_cargo_temp"
                  type="number"
                  value={params.initial_cargo_temp}
                  onChange={(e) => setParams({ ...params, initial_cargo_temp: Number(e.target.value) })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="max_iterations">{t('optimization.maxIterations')}</Label>
              <Input
                id="max_iterations"
                type="number"
                value={params.max_iterations}
                onChange={(e) => setParams({ ...params, max_iterations: Number(e.target.value) })}
              />
            </div>
            <Button
              className="w-full"
              onClick={handleStartOptimization}
              disabled={isOptimizing || isLoadingShipments || pendingCount === 0 || (depotInputMode === 'select' && !selectedDepotId)}
            >
              {isOptimizing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('optimization.optimizing')}
                </>
              ) : isLoadingShipments ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('optimization.checkingShipments')}
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  {t('optimization.startOptimization')}
                </>
              )}
            </Button>
            {!isLoadingShipments && pendingCount === 0 && (
              <p className="text-xs text-center text-warning mt-2">
                {totalShipments === 0
                  ? t('optimization.noShipmentsFound')
                  : t('optimization.allShipmentsAssigned')}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Progress & Results */}
      {currentResult && (
        <Card>
          <CardHeader>
            <CardTitle>{t('optimization.results')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {isOptimizing && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>{t('optimization.progress')}</span>
                  <span>{currentResult.progress}%</span>
                </div>
                <Progress value={currentResult.progress} />
              </div>
            )}

            {currentResult.status === 'completed' && (
              <>
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                  <div className="rounded-lg border p-4">
                    <p className="text-sm text-muted-foreground">{t('optimization.totalDistance')}</p>
                    <p className="text-2xl font-bold">{currentResult.totalDistance.toFixed(1)} km</p>
                  </div>
                  <div className="rounded-lg border p-4">
                    <p className="text-sm text-muted-foreground">{t('optimization.totalTime')}</p>
                    <p className="text-2xl font-bold">{currentResult.totalTime.toFixed(0)} min</p>
                  </div>
                  <div className="rounded-lg border p-4">
                    <p className="text-sm text-muted-foreground">{t('optimization.vehiclesUsed')}</p>
                    <p className="text-2xl font-bold">{currentResult.routes.length}</p>
                  </div>
                  <div className="rounded-lg border p-4">
                    <p className="text-sm text-muted-foreground">{t('optimization.feasibility')}</p>
                    <p className={`text-2xl font-bold ${currentResult.feasible ? 'text-green-600' : 'text-red-600'}`}>
                      {currentResult.feasible ? t('optimization.feasible') : t('optimization.infeasible')}
                    </p>
                  </div>
                </div>
                <Button onClick={handleViewOnMap}>
                  <Map className="mr-2 h-4 w-4" />
                  {t('optimization.viewOnMap')}
                </Button>
              </>
            )}

            {currentResult.status === 'failed' && (
              <div className="rounded-lg border border-destructive p-4 text-destructive">
                <p>{t('optimization.optimizationFailed')}</p>
                {currentResult.message && <p className="text-sm">{currentResult.message}</p>}
              </div>
            )}

            {/* Violations Section */}
            {currentResult.status === 'completed' && violations && (
              (violations.summary.total_temp_violations > 0 || violations.summary.total_unassigned > 0) && (
                <div className="space-y-4 mt-4">
                  <h3 className="text-lg font-semibold flex items-center gap-2 text-amber-600">
                    <AlertTriangle className="h-5 w-5" />
                    {t('optimization.violations', 'Constraint Violations')}
                  </h3>

                  {/* Temperature Violations */}
                  {violations.temperature_violations.length > 0 && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                      <h4 className="font-medium flex items-center gap-2 text-amber-700 mb-3">
                        <Thermometer className="h-4 w-4" />
                        {t('optimization.tempViolations', 'Temperature Violations')} ({violations.temperature_violations.length})
                      </h4>
                      <div className="space-y-2">
                        {violations.temperature_violations.map((v, idx) => (
                          <div key={idx} className="text-sm bg-white rounded p-2 border border-amber-100">
                            <div className="flex justify-between">
                              <span className="font-medium">{v.order_number}</span>
                              <span className={`px-2 py-0.5 rounded text-xs ${v.sla_tier === 'STRICT' ? 'bg-red-100 text-red-700' : 'bg-gray-100'}`}>
                                {v.sla_tier}
                              </span>
                            </div>
                            <div className="text-muted-foreground text-xs mt-1">{v.address}</div>
                            <div className="mt-1 text-amber-700">
                              {t('optimization.predictedTemp', 'Predicted')}: <span className="font-bold">{v.predicted_temp.toFixed(1)}°C</span>
                              {' > '}
                              {t('optimization.tempLimit', 'Limit')}: <span className="font-bold">{v.temp_limit.toFixed(1)}°C</span>
                              {' '}
                              <span className="text-red-600">(+{v.violation_amount.toFixed(1)}°C)</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Unassigned Shipments */}
                  {violations.unassigned_shipments.length > 0 && (
                    <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                      <h4 className="font-medium flex items-center gap-2 text-red-700 mb-3">
                        <PackageX className="h-4 w-4" />
                        {t('optimization.unassignedShipments', 'Unassigned Shipments')} ({violations.unassigned_shipments.length})
                      </h4>
                      <div className="space-y-3">
                        {violations.unassigned_shipments.map((s, idx) => (
                          <div key={idx} className="text-sm bg-white rounded p-3 border border-red-100">
                            <div className="flex justify-between">
                              <span className="font-medium">{s.order_number}</span>
                              <span className={`px-2 py-0.5 rounded text-xs ${s.sla_tier === 'STRICT' ? 'bg-red-100 text-red-700' : 'bg-gray-100'}`}>
                                {s.sla_tier}
                              </span>
                            </div>
                            <div className="text-muted-foreground text-xs mt-1">{s.address}</div>
                            <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                              <div>
                                <span className="text-muted-foreground">{t('optimization.timeWindow', 'Time Window')}:</span>
                                <span className="ml-1 font-medium">{s.time_windows}</span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">{t('optimization.tempLimit', 'Temp Limit')}:</span>
                                <span className="ml-1 font-medium">{s.temp_limit}°C</span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">{t('optimization.weight', 'Weight')}:</span>
                                <span className="ml-1 font-medium">{s.weight_kg} kg</span>
                              </div>
                            </div>
                            {/* Likely Reasons */}
                            {s.likely_reasons && s.likely_reasons.length > 0 && (
                              <div className="mt-2 pt-2 border-t border-red-100">
                                <div className="text-xs font-medium text-red-700 mb-1">
                                  {t('optimization.likelyReasons', 'Likely Reasons')}:
                                </div>
                                {s.likely_reasons.map((reason, rIdx) => (
                                  <div key={rIdx} className="text-xs bg-red-50 rounded p-2 mt-1">
                                    <div className="flex items-start gap-2">
                                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                        reason.type === 'TIME_WINDOW' ? 'bg-blue-100 text-blue-700' :
                                        reason.type === 'TEMPERATURE' ? 'bg-orange-100 text-orange-700' :
                                        reason.type === 'STRICT_SLA' ? 'bg-red-100 text-red-700' :
                                        'bg-gray-100 text-gray-700'
                                      }`}>
                                        {reason.type.replace('_', ' ')}
                                      </span>
                                      <span className="text-gray-700">{reason.message}</span>
                                    </div>
                                    <div className="mt-1 text-[11px] text-gray-500">
                                      <span className="font-medium">{t('optimization.parameter', 'Parameter')}:</span> {reason.parameter}
                                      {' | '}
                                      <span className="font-medium">{t('optimization.currentValue', 'Value')}:</span> {reason.current_value}
                                      {' → '}
                                      <span className="font-medium">{t('optimization.constraintValue', 'Constraint')}:</span> {reason.constraint_value}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
