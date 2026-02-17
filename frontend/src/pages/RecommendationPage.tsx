import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Sparkles,
  Eye,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Trash2,
  Plus,
  Search,
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
import { Input } from '@/components/ui/input'
import {
  insertionAPI,
  recommendationAPI,
  RouteListItem,
  VehicleRecommendation,
  RecommendationResponse,
} from '@/services/api'

function ConfidenceBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    HIGH: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
    MEDIUM: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
    LOW: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[level] || colors.LOW}`}>
      {level === 'HIGH' && <CheckCircle2 className="w-3 h-3 mr-1" />}
      {level === 'MEDIUM' && <AlertTriangle className="w-3 h-3 mr-1" />}
      {level === 'LOW' && <XCircle className="w-3 h-3 mr-1" />}
      {level}
    </span>
  )
}

function AffinityScore({ score }: { score: number }) {
  const color =
    score > 0.7
      ? 'text-emerald-600 dark:text-emerald-400'
      : score >= 0.4
        ? 'text-amber-600 dark:text-amber-400'
        : 'text-red-600 dark:text-red-400'
  return <span className={`font-mono font-semibold ${color}`}>{score.toFixed(3)}</span>
}

interface CoordRow {
  latitude: string
  longitude: string
}

export default function RecommendationPage() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('recommend')
  const [selectedRouteId, setSelectedRouteId] = useState<string>('')
  const [result, setResult] = useState<RecommendationResponse | null>(null)
  const [previewResult, setPreviewResult] = useState<RecommendationResponse | null>(null)
  const [coords, setCoords] = useState<CoordRow[]>([
    { latitude: '', longitude: '' },
    { latitude: '', longitude: '' },
  ])

  // Fetch routes (reuse insertionAPI.getRoutes)
  const { data: routesData, isLoading: routesLoading } = useQuery({
    queryKey: ['routes-for-recommendation'],
    queryFn: () => insertionAPI.getRoutes(),
  })

  // Recommend mutation
  const recommendMutation = useMutation({
    mutationFn: () => recommendationAPI.forRoute(selectedRouteId),
    onSuccess: (data) => {
      setResult(data)
      toast.success(t('recommendation.resultsReady'))
    },
    onError: () => {
      toast.error(t('recommendation.fetchFailed'))
    },
  })

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: () => {
      const parsed = coords
        .filter((c) => c.latitude && c.longitude)
        .map((c) => ({ latitude: Number(c.latitude), longitude: Number(c.longitude) }))
      return recommendationAPI.preview(parsed)
    },
    onSuccess: (data) => {
      setPreviewResult(data)
      toast.success(t('recommendation.resultsReady'))
    },
    onError: () => {
      toast.error(t('recommendation.fetchFailed'))
    },
  })

  // Accept mutation
  const acceptMutation = useMutation({
    mutationFn: (vehicleId: string) => recommendationAPI.accept(selectedRouteId, vehicleId),
    onSuccess: () => {
      toast.success(t('recommendation.assigned'))
    },
    onError: () => {
      toast.error(t('recommendation.assignFailed'))
    },
  })

  const routes: RouteListItem[] = routesData?.items || []

  const validCoords = coords.filter((c) => c.latitude && c.longitude)

  const updateCoord = (index: number, field: keyof CoordRow, value: string) => {
    setCoords((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)))
  }

  const addCoordRow = () => {
    setCoords((prev) => [...prev, { latitude: '', longitude: '' }])
  }

  const removeCoordRow = (index: number) => {
    setCoords((prev) => prev.filter((_, i) => i !== index))
  }

  const renderRecommendationTable = (
    recommendations: VehicleRecommendation[],
    showAssign: boolean
  ) => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('recommendation.rank')}</TableHead>
          <TableHead>{t('recommendation.licensePlate')}</TableHead>
          <TableHead>{t('recommendation.driverName')}</TableHead>
          <TableHead>{t('recommendation.affinityScore')}</TableHead>
          <TableHead>{t('recommendation.confidence')}</TableHead>
          {showAssign && <TableHead></TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {recommendations.map((rec, idx) => (
          <TableRow key={rec.vehicle_id}>
            <TableCell className="font-medium">#{idx + 1}</TableCell>
            <TableCell className="font-mono">{rec.license_plate}</TableCell>
            <TableCell>{rec.driver_name || '—'}</TableCell>
            <TableCell>
              <AffinityScore score={rec.affinity_score} />
            </TableCell>
            <TableCell>
              <ConfidenceBadge level={rec.confidence} />
            </TableCell>
            {showAssign && (
              <TableCell>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={acceptMutation.isPending}
                  onClick={() => acceptMutation.mutate(rec.vehicle_id)}
                >
                  {acceptMutation.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    t('recommendation.assign')
                  )}
                </Button>
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )

  const renderSignature = (signature: string[]) => (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {signature.map((cell) => (
        <span
          key={cell}
          className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-mono bg-muted text-muted-foreground"
        >
          {cell}
        </span>
      ))}
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('recommendation.title')}</h1>
        <p className="text-muted-foreground">{t('recommendation.subtitle')}</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="recommend" className="gap-2">
            <Sparkles className="h-4 w-4" />
            {t('recommendation.tabRecommend')}
          </TabsTrigger>
          <TabsTrigger value="preview" className="gap-2">
            <Eye className="h-4 w-4" />
            {t('recommendation.tabPreview')}
          </TabsTrigger>
        </TabsList>

        {/* ─── Recommend Tab ─── */}
        <TabsContent value="recommend" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">{t('recommendation.selectRoute')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">{t('recommendation.route')}</label>
                  <Select
                    value={selectedRouteId}
                    onValueChange={(v) => {
                      setSelectedRouteId(v)
                      setResult(null)
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue
                        placeholder={
                          routesLoading
                            ? t('common.loading')
                            : t('recommendation.chooseRoute')
                        }
                      />
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
              </div>

              <Button
                onClick={() => recommendMutation.mutate()}
                disabled={!selectedRouteId || recommendMutation.isPending}
              >
                {recommendMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Search className="mr-2 h-4 w-4" />
                )}
                {t('recommendation.getRecommendations')}
              </Button>
            </CardContent>
          </Card>

          {result && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-primary" />
                  {t('recommendation.results')}
                </CardTitle>
                {result.route_signature.length > 0 && (
                  <div>
                    <span className="text-sm text-muted-foreground">
                      {t('recommendation.routeSignature')}:
                    </span>
                    {renderSignature(result.route_signature)}
                  </div>
                )}
              </CardHeader>
              <CardContent>
                {result.recommendations.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    {t('recommendation.noResults')}
                  </p>
                ) : (
                  renderRecommendationTable(result.recommendations, true)
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ─── Preview Tab ─── */}
        <TabsContent value="preview" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">{t('recommendation.enterCoordinates')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                {coords.map((row, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground w-6">#{idx + 1}</span>
                    <Input
                      type="number"
                      step="any"
                      placeholder={t('recommendation.latitude')}
                      value={row.latitude}
                      onChange={(e) => updateCoord(idx, 'latitude', e.target.value)}
                      className="w-40"
                    />
                    <Input
                      type="number"
                      step="any"
                      placeholder={t('recommendation.longitude')}
                      value={row.longitude}
                      onChange={(e) => updateCoord(idx, 'longitude', e.target.value)}
                      className="w-40"
                    />
                    {coords.length > 2 && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => removeCoordRow(idx)}
                        className="h-8 w-8"
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>

              <div className="flex gap-3">
                <Button variant="outline" size="sm" onClick={addCoordRow}>
                  <Plus className="mr-1 h-3 w-3" />
                  {t('recommendation.addRow')}
                </Button>

                <Button
                  onClick={() => previewMutation.mutate()}
                  disabled={validCoords.length < 2 || previewMutation.isPending}
                >
                  {previewMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="mr-2 h-4 w-4" />
                  )}
                  {t('recommendation.analyze')}
                </Button>
              </div>
            </CardContent>
          </Card>

          {previewResult && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-primary" />
                  {t('recommendation.results')}
                </CardTitle>
                {previewResult.route_signature.length > 0 && (
                  <div>
                    <span className="text-sm text-muted-foreground">
                      {t('recommendation.routeSignature')}:
                    </span>
                    {renderSignature(previewResult.route_signature)}
                  </div>
                )}
              </CardHeader>
              <CardContent>
                {previewResult.recommendations.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    {t('recommendation.noResults')}
                  </p>
                ) : (
                  renderRecommendationTable(previewResult.recommendations, false)
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
