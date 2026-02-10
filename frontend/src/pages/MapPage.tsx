import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import L from 'leaflet'
import { Layers, Eye, EyeOff, Thermometer, Route as RouteIcon, AlertCircle, RefreshCw, MapPin } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { useOptimizationStore, RouteResult, RouteStop } from '@/stores/optimizationStore'
import { routesAPI } from '@/services/api'
import 'leaflet/dist/leaflet.css'

// Fix default marker icon issue with webpack
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
})

// OSRM public routing API
const OSRM_API_URL = 'https://router.project-osrm.org/route/v1/driving'

// Route colors
const ROUTE_COLORS = [
  '#e6194B', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
  '#42d4f4', '#f032e6', '#bfef45', '#fabed4', '#469990',
]

interface MapControllerProps {
  center: [number, number]
  routes: RouteResult[]
}

function MapController({ center, routes }: MapControllerProps) {
  const map = useMap()

  useEffect(() => {
    if (routes.length > 0) {
      const allPoints: [number, number][] = []
      routes.forEach((route) => {
        route.stops.forEach((stop) => {
          allPoints.push([stop.lat, stop.lon])
        })
      })
      if (allPoints.length > 0) {
        const bounds = L.latLngBounds(allPoints)
        map.fitBounds(bounds, { padding: [50, 50] })
      }
    } else {
      map.setView(center, 12)
    }
  }, [center, routes, map])

  return null
}

function createNumberIcon(number: number, color: string): L.DivIcon {
  return L.divIcon({
    className: 'custom-div-icon',
    html: `<div style="
      background-color: ${color};
      color: white;
      font-weight: bold;
      font-size: 12px;
      border-radius: 50%;
      width: 24px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 2px solid white;
      box-shadow: 0 2px 5px rgba(0,0,0,0.3);
    ">${number}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })
}

const depotIcon = L.divIcon({
  className: 'custom-div-icon',
  html: `<div style="
    background-color: #000;
    color: white;
    font-size: 14px;
    border-radius: 50%;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 3px solid white;
    box-shadow: 0 2px 5px rgba(0,0,0,0.3);
  ">D</div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
})

/**
 * Fetch road geometry from OSRM API
 * @param coordinates Array of [lat, lon] coordinates
 * @returns Array of [lat, lon] coordinates following roads
 */
async function fetchRoadGeometry(coordinates: [number, number][]): Promise<[number, number][]> {
  if (coordinates.length < 2) {
    return coordinates
  }

  // OSRM uses lon,lat format
  const coordsStr = coordinates.map(([lat, lon]) => `${lon},${lat}`).join(';')
  const url = `${OSRM_API_URL}/${coordsStr}?overview=full&geometries=geojson&steps=false`

  try {
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`OSRM API error: ${response.status}`)
    }

    const data = await response.json()

    if (data.code === 'Ok' && data.routes && data.routes[0]) {
      // Convert [lon, lat] to [lat, lon] format
      const routeCoords = data.routes[0].geometry.coordinates
      return routeCoords.map((coord: [number, number]) => [coord[1], coord[0]] as [number, number])
    }

    return coordinates
  } catch (error) {
    console.warn('OSRM routing failed, using straight lines:', error)
    return coordinates
  }
}

export default function MapPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { currentResult, setResult } = useOptimizationStore()
  const [visibleRoutes, setVisibleRoutes] = useState<Set<number>>(new Set())
  const [showDepot, setShowDepot] = useState(true)
  const [useRoadRouting, setUseRoadRouting] = useState(true)
  const [routeGeometries, setRouteGeometries] = useState<Map<number, [number, number][]>>(new Map())
  const [isLoadingRoutes, setIsLoadingRoutes] = useState(false)
  const [isFetchingData, setIsFetchingData] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const hasFetchedRef = useRef(false)

  // Independent data fetching: if store has taskId + planDate but no routes, fetch them
  useEffect(() => {
    if (hasFetchedRef.current) return
    if (!currentResult) return
    if (currentResult.status !== 'completed') return
    if (currentResult.routes.length > 0) return
    if (!currentResult.planDate || !currentResult.taskId) return

    hasFetchedRef.current = true
    const fetchRouteData = async () => {
      setIsFetchingData(true)
      setFetchError(null)
      try {
        const routeData = await routesAPI.getForMap(currentResult.planDate!, currentResult.taskId)
        const mappedRoutes = routeData.routes.map((r) => ({
          vehicleId: r.vehicleId,
          licensePlate: r.licensePlate,
          color: '',
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
        }))
        setResult({
          ...currentResult,
          routes: mappedRoutes,
          depot: routeData.depot || currentResult.depot,
        })
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error'
        setFetchError(message)
      } finally {
        setIsFetchingData(false)
      }
    }
    fetchRouteData()
  }, [currentResult, setResult])

  const handleRetryFetch = () => {
    hasFetchedRef.current = false
    setFetchError(null)
    // Trigger re-render to re-run the effect
    setIsFetchingData(false)
  }

  // Use depot from optimization result or default
  const depotCoords = currentResult?.depot || { lat: 25.033, lon: 121.5654 }
  const depot = useMemo<[number, number]>(
    () => [depotCoords.lat, depotCoords.lon],
    [depotCoords.lat, depotCoords.lon]
  )
  const routes = useMemo(() => currentResult?.routes || [], [currentResult?.routes])

  // Get straight-line coordinates for a route
  const getStraightLineCoordinates = useCallback((stops: RouteStop[]): [number, number][] => {
    const coords: [number, number][] = [depot]
    stops.forEach((stop) => {
      coords.push([stop.lat, stop.lon])
    })
    coords.push(depot)
    return coords
  }, [depot])

  // Fetch road geometries for all routes
  const fetchAllRoadGeometries = useCallback(async () => {
    if (!useRoadRouting || routes.length === 0) {
      setRouteGeometries(new Map())
      return
    }

    setIsLoadingRoutes(true)
    const newGeometries = new Map<number, [number, number][]>()

    for (let i = 0; i < routes.length; i++) {
      const straightCoords = getStraightLineCoordinates(routes[i].stops)
      try {
        const roadCoords = await fetchRoadGeometry(straightCoords)
        newGeometries.set(i, roadCoords)
      } catch {
        newGeometries.set(i, straightCoords)
      }
      // Small delay between requests to avoid rate limiting
      if (i < routes.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 200))
      }
    }

    setRouteGeometries(newGeometries)
    setIsLoadingRoutes(false)
  }, [routes, useRoadRouting, getStraightLineCoordinates])

  // Initialize visible routes
  useEffect(() => {
    setVisibleRoutes(new Set(routes.map((_, i) => i)))
  }, [routes.length])

  // Fetch road geometries when routes change or routing toggle changes
  useEffect(() => {
    fetchAllRoadGeometries()
  }, [fetchAllRoadGeometries])

  const toggleRoute = (index: number) => {
    setVisibleRoutes((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(index)) {
        newSet.delete(index)
      } else {
        newSet.add(index)
      }
      return newSet
    })
  }

  const getRouteCoordinates = (routeIndex: number, stops: RouteStop[]): [number, number][] => {
    if (useRoadRouting && routeGeometries.has(routeIndex)) {
      return routeGeometries.get(routeIndex)!
    }
    return getStraightLineCoordinates(stops)
  }

  // Empty state: no optimization result at all
  if (!currentResult) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight">{t('map.title')}</h1>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <MapPin className="h-12 w-12 text-muted-foreground mb-4" />
            <h2 className="text-lg font-semibold mb-2">{t('map.noOptimizationResult', 'No Optimization Results')}</h2>
            <p className="text-sm text-muted-foreground mb-6 max-w-md">
              {t('map.runOptimizationFirst', 'Run an optimization first to see routes on the map.')}
            </p>
            <Button onClick={() => navigate('/optimization')}>
              {t('map.goToOptimization', 'Go to Optimization')}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">{t('map.title')}</h1>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        {/* Map */}
        <div className="lg:col-span-3">
          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <div className="h-[600px] relative">
                {/* Loading overlay for fetching route data from API */}
                {isFetchingData && (
                  <div className="absolute inset-0 z-[1000] bg-white/70 flex flex-col items-center justify-center gap-3">
                    <div className="h-8 w-8 border-3 border-primary border-t-transparent rounded-full animate-spin" />
                    <span className="text-sm font-medium">{t('map.fetchingRouteData', 'Fetching route data...')}</span>
                  </div>
                )}
                {/* Error overlay for failed route data fetch */}
                {fetchError && (
                  <div className="absolute inset-0 z-[1000] bg-white/90 flex flex-col items-center justify-center gap-3">
                    <AlertCircle className="h-10 w-10 text-destructive" />
                    <p className="text-sm font-medium text-destructive">{t('map.fetchError', 'Failed to load route data')}</p>
                    <p className="text-xs text-muted-foreground max-w-sm text-center">{fetchError}</p>
                    <Button variant="outline" size="sm" onClick={handleRetryFetch}>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      {t('map.retry', 'Retry')}
                    </Button>
                  </div>
                )}
                {isLoadingRoutes && (
                  <div className="absolute top-2 left-2 z-[1000] bg-white/90 px-3 py-1.5 rounded-md shadow text-sm flex items-center gap-2">
                    <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                    {t('map.loadingRoutes')}
                  </div>
                )}
                <MapContainer
                  center={depot}
                  zoom={12}
                  style={{ height: '100%', width: '100%' }}
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  <MapController center={depot} routes={routes} />

                  {/* Depot marker */}
                  {showDepot && (
                    <Marker position={depot} icon={depotIcon}>
                      <Popup>
                        <div className="text-center">
                          <strong>Depot / Warehouse</strong>
                          <br />
                          <span className="text-sm text-gray-500">
                            {depot[0].toFixed(4)}, {depot[1].toFixed(4)}
                          </span>
                        </div>
                      </Popup>
                    </Marker>
                  )}

                  {/* Routes */}
                  {routes.map((route, routeIndex) => {
                    if (!visibleRoutes.has(routeIndex)) return null
                    const color = route.color || ROUTE_COLORS[routeIndex % ROUTE_COLORS.length]
                    const coordinates = getRouteCoordinates(routeIndex, route.stops)

                    return (
                      <div key={routeIndex}>
                        {/* Route line */}
                        <Polyline
                          positions={coordinates}
                          color={color}
                          weight={4}
                          opacity={0.8}
                        />

                        {/* Stop markers */}
                        {route.stops.map((stop) => (
                          <Marker
                            key={`${routeIndex}-${stop.sequence}`}
                            position={[stop.lat, stop.lon]}
                            icon={createNumberIcon(stop.sequence, color)}
                          >
                            <Popup>
                              <div className="min-w-[200px]">
                                <strong>#{stop.sequence} {stop.customerName}</strong>
                                <br />
                                <span className="text-sm text-gray-600">{stop.address}</span>
                                <hr className="my-2" />
                                <div className="text-sm">
                                  <p><strong>{t('map.arrivalTime')}:</strong> {stop.arrivalTime}</p>
                                  <p className="flex items-center gap-1">
                                    <Thermometer className="h-3 w-3" />
                                    <strong>{t('map.temperature')}:</strong>{' '}
                                    <span className={stop.feasible ? 'text-green-600' : 'text-red-600'}>
                                      {stop.temperature.toFixed(1)}°C
                                    </span>
                                    {' / '}
                                    {stop.tempLimit.toFixed(1)}°C
                                  </p>
                                </div>
                              </div>
                            </Popup>
                          </Marker>
                        ))}
                      </div>
                    )
                  })}
                </MapContainer>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Layer control */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Layers className="h-4 w-4" />
                {t('map.layers')}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Road routing toggle */}
              <div className="flex items-center justify-between">
                <Label htmlFor="road-routing" className="flex items-center gap-2 text-sm cursor-pointer">
                  <RouteIcon className="h-4 w-4" />
                  {t('map.roadRouting')}
                </Label>
                <Switch
                  id="road-routing"
                  checked={useRoadRouting}
                  onCheckedChange={setUseRoadRouting}
                />
              </div>

              <div className="border-t pt-4 space-y-2">
                <Button
                  variant={showDepot ? 'default' : 'outline'}
                  size="sm"
                  className="w-full justify-start"
                  onClick={() => setShowDepot(!showDepot)}
                >
                  {showDepot ? <Eye className="mr-2 h-4 w-4" /> : <EyeOff className="mr-2 h-4 w-4" />}
                  {t('map.showDepot')}
                </Button>

                {routes.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4 text-center">
                    {t('common.none')}
                  </p>
                ) : (
                  routes.map((route, index) => {
                    const color = route.color || ROUTE_COLORS[index % ROUTE_COLORS.length]
                    const isVisible = visibleRoutes.has(index)

                    return (
                      <Button
                        key={index}
                        variant={isVisible ? 'default' : 'outline'}
                        size="sm"
                        className="w-full justify-start"
                        style={{
                          backgroundColor: isVisible ? color : undefined,
                          borderColor: color,
                          color: isVisible ? 'white' : color,
                        }}
                        onClick={() => toggleRoute(index)}
                      >
                        {isVisible ? <Eye className="mr-2 h-4 w-4" /> : <EyeOff className="mr-2 h-4 w-4" />}
                        {route.licensePlate || `Route ${index + 1}`}
                        <span className="ml-auto text-xs">
                          ({route.stops.length})
                        </span>
                      </Button>
                    )
                  })
                )}
              </div>
            </CardContent>
          </Card>

          {currentResult && currentResult.status === 'completed' && (
            <Card className="mt-4">
              <CardHeader>
                <CardTitle className="text-base">{t('map.routeInfo')}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p>
                  <strong>{t('optimization.totalDistance')}:</strong>{' '}
                  {currentResult.totalDistance.toFixed(1)} km
                </p>
                <p>
                  <strong>{t('optimization.totalTime')}:</strong>{' '}
                  {currentResult.totalTime.toFixed(0)} min
                </p>
                <p>
                  <strong>{t('optimization.vehiclesUsed')}:</strong>{' '}
                  {currentResult.routes.length}
                </p>
                <p>
                  <strong>{t('optimization.feasibility')}:</strong>{' '}
                  <span className={currentResult.feasible ? 'text-green-600' : 'text-red-600'}>
                    {currentResult.feasible ? t('optimization.feasible') : t('optimization.infeasible')}
                  </span>
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
