import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useDropzone } from 'react-dropzone'
import toast from 'react-hot-toast'
import { Loader2, Upload, Download, FileSpreadsheet, CheckCircle, XCircle, AlertCircle, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { excelAPI } from '@/services/api'

interface RowError {
  row: number
  error: string
}

interface ImportResult {
  status: 'success' | 'partial' | 'error'
  importedCount?: number
  errorCount?: number
  errors?: string[]
  errorDetails?: RowError[]
}

export default function ImportPage() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<'vehicles' | 'shipments'>('vehicles')
  const [isUploading, setIsUploading] = useState(false)
  const [lastResult, setLastResult] = useState<ImportResult | null>(null)

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0]
    if (!file) return

    setIsUploading(true)
    setLastResult(null)

    try {
      const result = activeTab === 'vehicles'
        ? await excelAPI.importVehicles(file)
        : await excelAPI.importShipments(file)

      const importedCount = result.imported ?? result.count ?? 0
      const errorCount = result.errors ?? 0
      const errorDetails = result.error_details ?? []

      if (errorCount > 0 && importedCount > 0) {
        // Partial success - some rows imported, some failed
        setLastResult({
          status: 'partial',
          importedCount,
          errorCount,
          errorDetails,
        })
        toast.success(t('excel.partialSuccess', { imported: importedCount, failed: errorCount }), {
          icon: '⚠️',
          duration: 5000,
        })
      } else if (errorCount > 0 && importedCount === 0) {
        // All rows failed
        setLastResult({
          status: 'error',
          importedCount: 0,
          errorCount,
          errorDetails,
        })
        toast.error(t('excel.importFailed'))
      } else {
        // Full success
        setLastResult({
          status: 'success',
          importedCount,
          errorCount: 0,
        })
        toast.success(t('excel.importSuccess'))
      }
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } }; message?: string }
      const errorMessage = axiosError?.response?.data?.detail || axiosError?.message || t('excel.importFailed')
      setLastResult({ status: 'error', errors: [errorMessage] })
      toast.error(t('excel.importFailed'))
    } finally {
      setIsUploading(false)
    }
  }, [activeTab, t])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    maxFiles: 1,
    disabled: isUploading,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('import.title')}</h1>
        <p className="text-muted-foreground mt-1">{t('import.description')}</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Import Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5" />
              {t('excel.title')}
            </CardTitle>
            <CardDescription>{t('excel.supportedFormats')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Tab Selection */}
            <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v as 'vehicles' | 'shipments'); setLastResult(null) }}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="vehicles">{t('excel.importVehicles')}</TabsTrigger>
                <TabsTrigger value="shipments">{t('excel.importShipments')}</TabsTrigger>
              </TabsList>

              <TabsContent value="vehicles" className="mt-4">
                <p className="text-sm text-muted-foreground mb-4">
                  {t('import.vehiclesHint')}
                </p>
              </TabsContent>

              <TabsContent value="shipments" className="mt-4">
                <p className="text-sm text-muted-foreground mb-4">
                  {t('import.shipmentsHint')}
                </p>
              </TabsContent>
            </Tabs>

            {/* Dropzone */}
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                isUploading
                  ? 'border-muted-foreground/25 cursor-not-allowed opacity-50'
                  : isDragActive
                    ? 'border-primary bg-primary/5'
                    : 'border-muted-foreground/25 hover:border-primary/50'
              }`}
            >
              <input {...getInputProps()} />
              {isUploading ? (
                <>
                  <Loader2 className="mx-auto h-10 w-10 animate-spin text-primary" />
                  <p className="mt-3 text-sm font-medium">{t('excel.importing')}</p>
                </>
              ) : (
                <>
                  <Upload className="mx-auto h-10 w-10 text-muted-foreground" />
                  <p className="mt-3 text-sm font-medium">
                    {isDragActive ? t('import.dropHere') : t('excel.dragDrop')}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('import.clickToSelect')}
                  </p>
                </>
              )}
            </div>

            {/* Import Result */}
            {lastResult && (
              <div className={`rounded-lg p-4 ${
                lastResult.status === 'success'
                  ? 'bg-green-50 border border-green-200'
                  : lastResult.status === 'partial'
                    ? 'bg-amber-50 border border-amber-200'
                    : 'bg-red-50 border border-red-200'
              }`}>
                <div className="flex items-start gap-3">
                  {lastResult.status === 'success' ? (
                    <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
                  ) : lastResult.status === 'partial' ? (
                    <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-600 mt-0.5" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className={`font-medium ${
                      lastResult.status === 'success'
                        ? 'text-green-800'
                        : lastResult.status === 'partial'
                          ? 'text-amber-800'
                          : 'text-red-800'
                    }`}>
                      {lastResult.status === 'success'
                        ? t('excel.importSuccess')
                        : lastResult.status === 'partial'
                          ? t('excel.partialSuccessTitle')
                          : t('excel.importFailed')
                      }
                    </p>

                    {/* Success count */}
                    {lastResult.importedCount !== undefined && lastResult.importedCount > 0 && (
                      <p className={`text-sm mt-1 ${
                        lastResult.status === 'success' ? 'text-green-700' : 'text-amber-700'
                      }`}>
                        {t('excel.rowsImported', { count: lastResult.importedCount })}
                      </p>
                    )}

                    {/* Error count for partial success */}
                    {lastResult.status === 'partial' && lastResult.errorCount !== undefined && (
                      <p className="text-sm text-amber-700 mt-1">
                        {t('excel.rowsFailed', { count: lastResult.errorCount })}
                      </p>
                    )}

                    {/* HTTP error messages */}
                    {lastResult.errors && lastResult.errors.length > 0 && (
                      <ul className="text-sm text-red-700 mt-2 list-disc list-inside">
                        {lastResult.errors.map((err, i) => (
                          <li key={i}>{err}</li>
                        ))}
                      </ul>
                    )}

                    {/* Row-level error details */}
                    {lastResult.errorDetails && lastResult.errorDetails.length > 0 && (
                      <div className="mt-3">
                        <p className={`text-sm font-medium mb-1 ${
                          lastResult.status === 'partial' ? 'text-amber-800' : 'text-red-800'
                        }`}>
                          {t('excel.errorDetails')}:
                        </p>
                        <div className={`max-h-32 overflow-y-auto rounded border p-2 text-xs ${
                          lastResult.status === 'partial'
                            ? 'bg-amber-100/50 border-amber-200'
                            : 'bg-red-100/50 border-red-200'
                        }`}>
                          <ul className="space-y-1">
                            {lastResult.errorDetails.slice(0, 10).map((detail, i) => (
                              <li key={i} className={
                                lastResult.status === 'partial' ? 'text-amber-800' : 'text-red-800'
                              }>
                                <span className="font-medium">{t('excel.row')} {detail.row}:</span> {detail.error}
                              </li>
                            ))}
                            {lastResult.errorDetails.length > 10 && (
                              <li className={`italic ${
                                lastResult.status === 'partial' ? 'text-amber-600' : 'text-red-600'
                              }`}>
                                {t('excel.moreErrors', { count: lastResult.errorDetails.length - 10 })}
                              </li>
                            )}
                          </ul>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Download Templates */}
            <div className="pt-4 border-t">
              <p className="text-sm font-medium mb-3">{t('import.downloadTemplates')}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" asChild>
                  <a href={excelAPI.downloadVehicleTemplate()} download>
                    <Download className="mr-2 h-4 w-4" />
                    {t('excel.vehicleTemplate')}
                  </a>
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <a href={excelAPI.downloadShipmentTemplate()} download>
                    <Download className="mr-2 h-4 w-4" />
                    {t('excel.shipmentTemplate')}
                  </a>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Instructions Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              {t('import.instructionsTitle')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium">
                  1
                </div>
                <p className="text-sm text-muted-foreground">{t('import.step1')}</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium">
                  2
                </div>
                <p className="text-sm text-muted-foreground">{t('import.step2')}</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium">
                  3
                </div>
                <p className="text-sm text-muted-foreground">{t('import.step3')}</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-medium">
                  4
                </div>
                <p className="text-sm text-muted-foreground">{t('import.step4')}</p>
              </div>
            </div>

            <div className="rounded-lg bg-muted p-4 mt-4">
              <p className="text-sm font-medium mb-2">{t('import.tipsTitle')}</p>
              <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside">
                <li>{t('import.tip1')}</li>
                <li>{t('import.tip2')}</li>
                <li>{t('import.tip3')}</li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
