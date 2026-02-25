import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  PlusCircle,
  Eye,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  History,
  Thermometer,
  Clock,
  MapPin,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  insertionAPI,
  shipmentAPI,
  InsertionCandidate,
  InsertionPreviewResponse,
  InsertionHistoryEntry,
  RouteListItem,
  Shipment,
} from '@/services/api'

function RiskBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    GREEN: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
    YELLOW: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
    RED: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[level] || colors.RED}`}>
      {level === 'GREEN' && <CheckCircle2 className="w-3 h-3 mr-1" />}
      {level === 'YELLOW' && <AlertTriangle className="w-3 h-3 mr-1" />}
      {level === 'RED' && <XCircle className="w-3 h-3 mr-1" />}
      {level}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ACCEPTED: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
    REJECTED: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    CONFLICT: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
    PENDING: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
      {status}
    </span>
  )
}

export default function InsertionPage() {
  const { t } = useTranslation()
  const [selectedRouteId, setSelectedRouteId] = useState<string>('')
  const [selectedShipmentId, setSelectedShipmentId] = useState<string>('')
  const [preview, setPreview] = useState<InsertionPreviewResponse | null>(null)
  const [activeTab, setActiveTab] = useState('insert')

  // Fetch routes
  const { data: routesData, isLoading: routesLoading } = useQuery({
    queryKey: ['routes-for-insertion'],
    queryFn: () => insertionAPI.getRoutes(),
  })

  // Fetch pending shipments
  const { data: shipments, isLoading: shipmentsLoading } = useQuery({
    queryKey: ['shipments-for-insertion'],
    queryFn: () => shipmentAPI.getAll(),
    select: (data: Shipment[]) => data.filter((s) => s.status === 'pending'),
  })

  // Fetch insertion history for selected route
  const { data: historyData, refetch: refetchHistory } = useQuery({
    queryKey: ['insertion-history', selectedRouteId],
    queryFn: () => insertionAPI.getHistory(selectedRouteId),
    enabled: !!selectedRouteId && activeTab === 'history',
  })

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: () => insertionAPI.preview(selectedRouteId, selectedShipmentId),
    onSuccess: (data) => {
      setPreview(data)
      toast.success(t('insertion.previewReady'))
    },
    onError: (error: { response?: { status: number; data?: { detail?: string } } }) => {
      if (error.response?.status === 404) {
        toast.error(t('insertion.routeOrShipmentNotFound'))
      } else {
        toast.error(t('insertion.previewFailed'))
      }
    },
  })

  // Insert mutation
  const insertMutation = useMutation({
    mutationFn: (position?: number) =>
      insertionAPI.insert(selectedRouteId, selectedShipmentId, position),
    onSuccess: (data) => {
      toast.success(
        `${t('insertion.insertSuccess')} — Position ${data.position}, Risk: ${data.temp_risk_level}`
      )
      setPreview(null)
      refetchHistory()
    },
    onError: (error: { response?: { status: number; data?: { detail?: { error?: string; message?: string; current_version?: number; reason?: string; temp_risk_score?: number } } } }) => {
      const detail = error.response?.data?.detail
      if (error.response?.status === 409) {
        toast.error(
          `${t('insertion.conflictError')} (v${detail?.current_version ?? '?'})`
        )
        setPreview(null)
      } else if (error.response?.status === 422) {
        toast.error(
          `${t('insertion.rejectedError')}: ${detail?.reason || 'Temperature risk too high'}`
        )
      } else {
        toast.error(t('insertion.insertFailed'))
      }
    },
  })

  const routes: RouteListItem[] = routesData?.items || []
  const history: InsertionHistoryEntry[] = historyData?.items || []

  const canPreview = selectedRouteId && selectedShipmentId
  const canInsert = preview && preview.candidates.some((c) => c.temp_risk_level !== 'RED')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('insertion.title')}</h1>
        <p className="text-muted-foreground">{t('insertion.subtitle')}</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="insert" className="gap-2">
            <PlusCircle className="h-4 w-4" />
            {t('insertion.tabInsert')}
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-2">
            <History className="h-4 w-4" />
            {t('insertion.tabHistory')}
          </TabsTrigger>
        </TabsList>

        {/* ─── Insert Tab ─── */}
        <TabsContent value="insert" className="space-y-4">
          {/* Selection Controls */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">{t('insertion.selectRouteAndShipment')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Route selector */}
                <div className="space-y-2">
                  <label className="text-sm font-medium">{t('insertion.selectRoute')}</label>
                  <Select value={selectedRouteId} onValueChange={(v) => { setSelectedRouteId(v); setPreview(null) }}>
                    <SelectTrigger>
                      <SelectValue placeholder={routesLoading ? t('common.loading') : t('insertion.chooseRoute')} />
                    </SelectTrigger>
                    <SelectContent>
                      {routes.map((r) => (
                        <SelectItem key={r.id} value={r.id}>
                          {r.route_code} — {r.total_stops} stops, {r.driver_name || 'No driver'}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Shipment selector */}
                <div className="space-y-2">
                  <label className="text-sm font-medium">{t('insertion.selectShipment')}</label>
                  <Select value={selectedShipmentId} onValueChange={(v) => { setSelectedShipmentId(v); setPreview(null) }}>
                    <SelectTrigger>
                      <SelectValue placeholder={shipmentsLoading ? t('common.loading') : t('insertion.chooseShipment')} />
                    </SelectTrigger>
                    <SelectContent>
                      {(shipments || []).map((s) => (
                        <SelectItem key={s.id} value={s.id}>
                          {s.customer_name} — {s.address.substring(0, 30)}...
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex gap-3">
                <Button
                  onClick={() => previewMutation.mutate()}
                  disabled={!canPreview || previewMutation.isPending}
                >
                  {previewMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Eye className="mr-2 h-4 w-4" />
                  )}
                  {t('insertion.preview')}
                </Button>

                <Button
                  variant="default"
                  onClick={() => insertMutation.mutate(undefined)}
                  disabled={!canInsert || insertMutation.isPending}
                >
                  {insertMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <PlusCircle className="mr-2 h-4 w-4" />
                  )}
                  {t('insertion.insertBest')}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Preview Results */}
          {preview && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Thermometer className="h-5 w-5 text-cold" />
                  {t('insertion.previewResults')}
                  <span className="text-sm font-normal text-muted-foreground">
                    (Route v{preview.route_version})
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t('insertion.position')}</TableHead>
                      <TableHead>{t('insertion.tempRisk')}</TableHead>
                      <TableHead>{t('insertion.riskLevel')}</TableHead>
                      <TableHead>{t('insertion.delay')}</TableHead>
                      <TableHead>{t('insertion.extraDistance')}</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.candidates.map((c: InsertionCandidate) => (
                      <TableRow
                        key={c.position}
                        className={c.position === preview.recommended_position ? 'bg-primary/5' : ''}
                      >
                        <TableCell className="font-medium">
                          <div className="flex items-center gap-2">
                            <MapPin className="h-4 w-4 text-muted-foreground" />
                            #{c.position}
                            {c.position === preview.recommended_position && (
                              <span className="text-xs bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                                {t('insertion.recommended')}
                              </span>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>{Number(c.temp_risk_score).toFixed(3)}</TableCell>
                        <TableCell><RiskBadge level={c.temp_risk_level} /></TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <Clock className="h-3 w-3 text-muted-foreground" />
                            +{c.delay_impact_minutes} min
                          </div>
                        </TableCell>
                        <TableCell>+{(c.extra_distance_meters / 1000).toFixed(1)} km</TableCell>
                        <TableCell>
                          <Button
                            size="sm"
                            variant={c.temp_risk_level === 'RED' ? 'destructive' : 'outline'}
                            disabled={c.temp_risk_level === 'RED' || insertMutation.isPending}
                            onClick={() => insertMutation.mutate(c.position)}
                          >
                            {insertMutation.isPending ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              t('insertion.insertHere')
                            )}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ─── History Tab ─── */}
        <TabsContent value="history" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">{t('insertion.historyTitle')}</CardTitle>
            </CardHeader>
            <CardContent>
              {!selectedRouteId ? (
                <p className="text-muted-foreground text-sm">{t('insertion.selectRouteFirst')}</p>
              ) : history.length === 0 ? (
                <p className="text-muted-foreground text-sm">{t('insertion.noHistory')}</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t('insertion.status')}</TableHead>
                      <TableHead>{t('insertion.position')}</TableHead>
                      <TableHead>{t('insertion.tempRisk')}</TableHead>
                      <TableHead>{t('insertion.delay')}</TableHead>
                      <TableHead>{t('insertion.extraDistance')}</TableHead>
                      <TableHead>{t('insertion.time')}</TableHead>
                      <TableHead>{t('insertion.reason')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.map((h: InsertionHistoryEntry) => (
                      <TableRow key={h.id}>
                        <TableCell><StatusBadge status={h.status} /></TableCell>
                        <TableCell>#{h.proposed_position}</TableCell>
                        <TableCell>{h.temp_risk_score != null ? Number(h.temp_risk_score).toFixed(3) : '—'}</TableCell>
                        <TableCell>{h.delay_impact_minutes != null ? `+${h.delay_impact_minutes} min` : '—'}</TableCell>
                        <TableCell>
                          {h.extra_distance_meters != null
                            ? `+${(h.extra_distance_meters / 1000).toFixed(1)} km`
                            : '—'}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {new Date(h.created_at).toLocaleString()}
                        </TableCell>
                        <TableCell className="text-xs max-w-[200px] truncate">
                          {h.rejection_reason || '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
