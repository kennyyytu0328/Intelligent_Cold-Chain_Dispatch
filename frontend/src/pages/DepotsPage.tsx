import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useDropzone } from 'react-dropzone'
import toast from 'react-hot-toast'
import { Plus, Pencil, Trash2, Loader2, Warehouse, MapPin, Navigation, Upload, Download, FileSpreadsheet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import api from '@/services/api'

interface Depot {
  id: string
  name: string
  code?: string
  address?: string
  latitude: number
  longitude: number
  is_active: boolean
  contact_person?: string
  contact_phone?: string
  created_at: string
  updated_at: string
}

const defaultDepot = {
  name: '',
  code: '',
  address: '',
  latitude: 25.033,
  longitude: 121.5654,
  is_active: true,
  contact_person: '',
  contact_phone: '',
}

export default function DepotsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [editingDepot, setEditingDepot] = useState<Depot | null>(null)
  const [formData, setFormData] = useState(defaultDepot)
  const [inputMode, setInputMode] = useState<'address' | 'coordinates'>('coordinates')
  const [isGeocoding, setIsGeocoding] = useState(false)
  const [showImportDialog, setShowImportDialog] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [importResult, setImportResult] = useState<any>(null)

  const { data: response, isLoading } = useQuery({
    queryKey: ['depots'],
    queryFn: async () => {
      const res = await api.get<{ total: number; depots: Depot[] }>('/depots')
      return res.data
    },
  })

  const depots = response?.depots || []

  const createMutation = useMutation({
    mutationFn: async (data: typeof defaultDepot) => {
      const res = await api.post('/depots', data)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['depots'] })
      toast.success(t('depots.saveSuccess'))
      setDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<typeof defaultDepot> }) => {
      const res = await api.patch(`/depots/${id}`, data)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['depots'] })
      toast.success(t('depots.updateSuccess'))
      setDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/depots/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['depots'] })
      toast.success(t('depots.deleteSuccess'))
      setDeleteDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const handleAdd = () => {
    setEditingDepot(null)
    setFormData(defaultDepot)
    setInputMode('coordinates')
    setDialogOpen(true)
  }

  const handleEdit = (depot: Depot) => {
    setEditingDepot(depot)
    setFormData({
      name: depot.name,
      code: depot.code || '',
      address: depot.address || '',
      latitude: depot.latitude,
      longitude: depot.longitude,
      is_active: depot.is_active,
      contact_person: depot.contact_person || '',
      contact_phone: depot.contact_phone || '',
    })
    setInputMode('coordinates')
    setDialogOpen(true)
  }

  const handleDelete = (depot: Depot) => {
    setEditingDepot(depot)
    setDeleteDialogOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingDepot) {
      updateMutation.mutate({ id: editingDepot.id, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  const handleConfirmDelete = () => {
    if (editingDepot) {
      deleteMutation.mutate(editingDepot.id)
    }
  }

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const file = acceptedFiles[0]
    if (!file) return

    setIsUploading(true)
    setImportResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await api.post<{
        total: number
        success: number
        skipped: number
        failed: number
        geocoded: number
        errors: string[]
      }>('/depots/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      setImportResult(response.data)

      if (response.data.success > 0) {
        queryClient.invalidateQueries({ queryKey: ['depots'] })
        toast.success(t('depots.importSuccess', { count: response.data.success }))
      }

      if (response.data.failed > 0 || response.data.skipped > 0) {
        toast.error(t('depots.importError', { failed: response.data.failed, skipped: response.data.skipped }))
      }
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || t('depots.convertFailed')
      toast.error(errorMsg)
    } finally {
      setIsUploading(false)
    }
  }, [queryClient])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    maxFiles: 1,
    disabled: isUploading,
  })

  const handleDownloadTemplate = () => {
    // Trigger download of template file from backend
    const link = document.createElement('a')
    link.href = '/ICCDDS_Depot_Template.xlsx'
    link.download = 'ICCDDS_Depot_Template.xlsx'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    toast.success(t('depots.templateDownloadSuccess'))
  }

  const handleGeocode = async () => {
    if (!formData.address || !formData.address.trim()) {
      toast.error(t('depots.enterAddress'))
      return
    }

    setIsGeocoding(true)
    try {
      const response = await api.post<{
        latitude: number
        longitude: number
        display_name: string
      }>('/geocode', {
        address: formData.address,
        country: 'Taiwan',
      })

      setFormData({
        ...formData,
        latitude: response.data.latitude,
        longitude: response.data.longitude,
      })

      toast.success(t('depots.convertSuccess'))
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || t('depots.convertFailed')
      toast.error(errorMsg)
    } finally {
      setIsGeocoding(false)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Warehouse className="h-6 w-6" />
          {t('depots.title')}
        </h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowImportDialog(true)}>
            <FileSpreadsheet className="mr-2 h-4 w-4" />
            {t('depots.importExcel')}
          </Button>
          <Button onClick={handleAdd}>
            <Plus className="mr-2 h-4 w-4" />
            {t('depots.addDepot')}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('depots.subtitle')}</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : depots.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">{t('common.none')}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('depots.name')}</TableHead>
                    <TableHead>{t('depots.code')}</TableHead>
                    <TableHead>{t('depots.address')}</TableHead>
                    <TableHead>{t('depots.coordinates')}</TableHead>
                    <TableHead>{t('depots.status')}</TableHead>
                    <TableHead className="text-right">{t('common.actions')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {depots.map((depot) => (
                    <TableRow key={depot.id}>
                      <TableCell className="font-medium">{depot.name}</TableCell>
                      <TableCell>{depot.code || '-'}</TableCell>
                      <TableCell className="max-w-[200px] truncate">{depot.address || '-'}</TableCell>
                      <TableCell className="text-sm">
                        {Number(depot.latitude).toFixed(4)}, {Number(depot.longitude).toFixed(4)}
                      </TableCell>
                      <TableCell>
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                            depot.is_active
                              ? 'bg-green-100 text-green-700'
                              : 'bg-gray-100 text-gray-700'
                          }`}
                        >
                          {depot.is_active ? t('depots.active') : t('depots.inactive')}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="ghost" size="icon" onClick={() => handleEdit(depot)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => handleDelete(depot)}>
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingDepot ? t('depots.editDepot') : t('depots.addDepot')}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">{t('depots.name')} *</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="code">{t('depots.code')}</Label>
                <Input
                  id="code"
                  value={formData.code}
                  onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                  placeholder="TP-001"
                />
              </div>
            </div>

            {/* Input Mode Toggle */}
            <div className="flex items-center gap-4 p-3 bg-muted rounded-lg">
              <Label className="text-sm font-medium">{t('depots.inputMode')}:</Label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={inputMode === 'address' ? 'default' : 'outline'}
                  onClick={() => setInputMode('address')}
                >
                  <MapPin className="mr-2 h-4 w-4" />
                  {t('depots.addressMode')}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={inputMode === 'coordinates' ? 'default' : 'outline'}
                  onClick={() => setInputMode('coordinates')}
                >
                  <Navigation className="mr-2 h-4 w-4" />
                  {t('depots.coordinatesMode')}
                </Button>
              </div>
            </div>

            {/* Address Input Mode */}
            {inputMode === 'address' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="address">{t('depots.address')} *</Label>
                  <div className="flex gap-2">
                    <Input
                      id="address"
                      value={formData.address}
                      onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                      placeholder="台北市信義區信義路五段7號"
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      onClick={handleGeocode}
                      disabled={isGeocoding || !formData.address}
                    >
                      {isGeocoding ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        t('depots.convert')
                      )}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t('depots.convertHint')}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="latitude">{t('depots.latitude')} ({t('depots.autoFilled')})</Label>
                    <Input
                      id="latitude"
                      type="number"
                      step="0.0001"
                      value={formData.latitude}
                      onChange={(e) => setFormData({ ...formData, latitude: Number(e.target.value) })}
                      required
                      readOnly
                      className="bg-muted"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="longitude">{t('depots.longitude')} ({t('depots.autoFilled')})</Label>
                    <Input
                      id="longitude"
                      type="number"
                      step="0.0001"
                      value={formData.longitude}
                      onChange={(e) => setFormData({ ...formData, longitude: Number(e.target.value) })}
                      required
                      readOnly
                      className="bg-muted"
                    />
                  </div>
                </div>
              </>
            )}

            {/* Coordinates Input Mode */}
            {inputMode === 'coordinates' && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="address-readonly">{t('depots.address')} ({t('depots.optional')})</Label>
                  <Input
                    id="address-readonly"
                    value={formData.address}
                    onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                    placeholder="Full street address"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="latitude-input">{t('depots.latitude')} *</Label>
                    <Input
                      id="latitude-input"
                      type="number"
                      step="0.0001"
                      value={formData.latitude}
                      onChange={(e) => setFormData({ ...formData, latitude: Number(e.target.value) })}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="longitude-input">{t('depots.longitude')} *</Label>
                    <Input
                      id="longitude-input"
                      type="number"
                      step="0.0001"
                      value={formData.longitude}
                      onChange={(e) => setFormData({ ...formData, longitude: Number(e.target.value) })}
                      required
                    />
                  </div>
                </div>
              </>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="contact_person">{t('depots.contactPerson')}</Label>
                <Input
                  id="contact_person"
                  value={formData.contact_person}
                  onChange={(e) => setFormData({ ...formData, contact_person: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="contact_phone">{t('depots.contactPhone')}</Label>
                <Input
                  id="contact_phone"
                  value={formData.contact_phone}
                  onChange={(e) => setFormData({ ...formData, contact_phone: e.target.value })}
                />
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={isSaving}>
                {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('common.save')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Excel Import Dialog */}
      <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5" />
              {t('depots.importTitle')}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {/* Download Template */}
            <div className="flex items-center justify-between p-4 bg-muted rounded-lg">
              <div>
                <p className="font-medium">{t('depots.needTemplate')}</p>
                <p className="text-sm text-muted-foreground">
                  {t('depots.templateDescription')}
                </p>
              </div>
              <Button variant="outline" onClick={handleDownloadTemplate}>
                <Download className="mr-2 h-4 w-4" />
                {t('depots.downloadTemplate')}
              </Button>
            </div>

            {/* Upload Area */}
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                isDragActive
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-primary/50'
              } ${isUploading ? 'pointer-events-none opacity-50' : ''}`}
            >
              <input {...getInputProps()} />
              {isUploading ? (
                <Loader2 className="mx-auto h-12 w-12 animate-spin text-muted-foreground" />
              ) : (
                <>
                  <Upload className="mx-auto h-12 w-12 text-muted-foreground" />
                  <p className="mt-4 text-sm font-medium">
                    {isDragActive ? t('depots.dropHere') : t('depots.dragDrop')}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t('depots.clickToSelect')}
                  </p>
                </>
              )}
            </div>

            {/* Import Result */}
            {importResult && (
              <div className="rounded-lg border p-4 space-y-2">
                <p className="font-medium">{t('depots.importResults')}</p>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>{t('depots.totalRows')}: {importResult.total}</div>
                  <div className="text-green-600">✓ {t('depots.successCount')}: {importResult.success}</div>
                  <div className="text-yellow-600">⊘ {t('depots.skippedCount')}: {importResult.skipped}</div>
                  <div className="text-red-600">✗ {t('depots.failedCount')}: {importResult.failed}</div>
                  <div className="text-blue-600">🌐 {t('depots.geocodedCount')}: {importResult.geocoded}</div>
                </div>

                {importResult.errors && importResult.errors.length > 0 && (
                  <div className="mt-4">
                    <p className="text-sm font-medium text-destructive">{t('depots.errors')}</p>
                    <div className="mt-2 max-h-32 overflow-y-auto text-xs space-y-1">
                      {importResult.errors.map((error: string, i: number) => (
                        <div key={i} className="text-muted-foreground">
                          • {error}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Instructions */}
            <div className="text-xs text-muted-foreground space-y-1">
              <p className="font-medium">{t('depots.instructions')}</p>
              <p>{t('depots.instruction1')}</p>
              <p>{t('depots.instruction2')}</p>
              <p>{t('depots.instruction3')}</p>
              <p>{t('depots.instruction4')}</p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => {
              setShowImportDialog(false)
              setImportResult(null)
            }}>
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('depots.deleteDepot')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t('depots.confirmDelete')}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button variant="destructive" onClick={handleConfirmDelete} disabled={deleteMutation.isPending}>
              {deleteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
