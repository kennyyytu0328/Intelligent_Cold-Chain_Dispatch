import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Pencil, Trash2, Loader2, RotateCcw } from 'lucide-react'
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
import { shipmentAPI, Shipment } from '@/services/api'

const defaultShipment: Omit<Shipment, 'id'> = {
  customer_name: '',
  address: '',
  latitude: 25.033,
  longitude: 121.565,
  weight_kg: 100,
  temp_min: 0,
  temp_max: 5,
  time_window_start: '08:00',
  time_window_end: '18:00',
  service_time_minutes: 15,
  priority: 'medium',
  status: 'pending',
}

export default function ShipmentsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [resetDialogOpen, setResetDialogOpen] = useState(false)
  const [editingShipment, setEditingShipment] = useState<Shipment | null>(null)
  const [formData, setFormData] = useState(defaultShipment)

  const { data: shipments = [], isLoading } = useQuery({
    queryKey: ['shipments'],
    queryFn: shipmentAPI.getAll,
  })

  const createMutation = useMutation({
    mutationFn: shipmentAPI.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shipments'] })
      toast.success(t('shipments.saveSuccess'))
      setDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Shipment> }) =>
      shipmentAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shipments'] })
      toast.success(t('shipments.saveSuccess'))
      setDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: shipmentAPI.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shipments'] })
      toast.success(t('shipments.deleteSuccess'))
      setDeleteDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const resetMutation = useMutation({
    mutationFn: shipmentAPI.resetAll,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['shipments'] })
      queryClient.invalidateQueries({ queryKey: ['routes'] })
      toast.success(t('shipments.resetSuccess', { count: data.shipments_reset }))
      setResetDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const handleAdd = () => {
    setEditingShipment(null)
    setFormData(defaultShipment)
    setDialogOpen(true)
  }

  const handleEdit = (shipment: Shipment) => {
    setEditingShipment(shipment)
    setFormData({
      customer_name: shipment.customer_name,
      address: shipment.address,
      latitude: shipment.latitude,
      longitude: shipment.longitude,
      weight_kg: shipment.weight_kg,
      temp_min: shipment.temp_min,
      temp_max: shipment.temp_max,
      time_window_start: shipment.time_window_start,
      time_window_end: shipment.time_window_end,
      service_time_minutes: shipment.service_time_minutes,
      priority: shipment.priority,
      status: shipment.status,
    })
    setDialogOpen(true)
  }

  const handleDelete = (shipment: Shipment) => {
    setEditingShipment(shipment)
    setDeleteDialogOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingShipment) {
      updateMutation.mutate({ id: editingShipment.id, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  const handleConfirmDelete = () => {
    if (editingShipment) {
      deleteMutation.mutate(editingShipment.id)
    }
  }

  const handleResetAll = () => {
    setResetDialogOpen(true)
  }

  const handleConfirmReset = () => {
    resetMutation.mutate()
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  const getStatusBadgeClass = (status: string) => {
    const normalizedStatus = status.toLowerCase()
    switch (normalizedStatus) {
      case 'pending':
        return 'bg-yellow-100 text-yellow-700'
      case 'assigned':
        return 'bg-blue-100 text-blue-700'
      case 'in_transit':
        return 'bg-purple-100 text-purple-700'
      case 'delivered':
        return 'bg-green-100 text-green-700'
      case 'failed':
        return 'bg-red-100 text-red-700'
      default:
        return 'bg-gray-100 text-gray-700'
    }
  }

  const getPriorityLabel = (priority: number | string): string => {
    // Handle both integer (0-100) and string ('high', 'medium', 'low') formats
    if (typeof priority === 'string') return priority
    if (priority >= 70) return 'high'
    if (priority >= 30) return 'medium'
    return 'low'
  }

  const getPriorityBadgeClass = (priority: number | string) => {
    const label = getPriorityLabel(priority)
    switch (label) {
      case 'high':
        return 'bg-red-100 text-red-700'
      case 'medium':
        return 'bg-yellow-100 text-yellow-700'
      case 'low':
        return 'bg-green-100 text-green-700'
      default:
        return 'bg-gray-100 text-gray-700'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">{t('shipments.title')}</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleResetAll}>
            <RotateCcw className="mr-2 h-4 w-4" />
            {t('shipments.resetAll')}
          </Button>
          <Button onClick={handleAdd}>
            <Plus className="mr-2 h-4 w-4" />
            {t('shipments.addShipment')}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('shipments.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : shipments.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">{t('common.none')}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('shipments.customerName')}</TableHead>
                    <TableHead>{t('shipments.address')}</TableHead>
                    <TableHead>{t('shipments.weight')}</TableHead>
                    <TableHead>{t('shipments.priority')}</TableHead>
                    <TableHead>{t('shipments.status')}</TableHead>
                    <TableHead className="text-right">{t('common.actions')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shipments.map((shipment) => (
                    <TableRow key={shipment.id}>
                      <TableCell className="font-medium">{shipment.customer_name}</TableCell>
                      <TableCell className="max-w-[200px] truncate">{shipment.address}</TableCell>
                      <TableCell>{shipment.weight_kg} kg</TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${getPriorityBadgeClass(shipment.priority)}`}>
                          {t(`shipments.priority${getPriorityLabel(shipment.priority).charAt(0).toUpperCase() + getPriorityLabel(shipment.priority).slice(1)}`)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${getStatusBadgeClass(shipment.status)}`}>
                          {t(`shipments.status${shipment.status.toLowerCase().split('_').map(s => s.charAt(0).toUpperCase() + s.slice(1)).join('')}`)}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="ghost" size="icon" onClick={() => handleEdit(shipment)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => handleDelete(shipment)}>
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
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingShipment ? t('shipments.editShipment') : t('shipments.addShipment')}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="customer_name">{t('shipments.customerName')}</Label>
              <Input
                id="customer_name"
                value={formData.customer_name}
                onChange={(e) => setFormData({ ...formData, customer_name: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="address">{t('shipments.address')}</Label>
              <Input
                id="address"
                value={formData.address}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="latitude">{t('shipments.latitude')}</Label>
                <Input
                  id="latitude"
                  type="number"
                  step="0.0001"
                  value={formData.latitude}
                  onChange={(e) => setFormData({ ...formData, latitude: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="longitude">{t('shipments.longitude')}</Label>
                <Input
                  id="longitude"
                  type="number"
                  step="0.0001"
                  value={formData.longitude}
                  onChange={(e) => setFormData({ ...formData, longitude: Number(e.target.value) })}
                  required
                />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="weight_kg">{t('shipments.weight')}</Label>
                <Input
                  id="weight_kg"
                  type="number"
                  value={formData.weight_kg}
                  onChange={(e) => setFormData({ ...formData, weight_kg: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="temp_min">{t('shipments.tempMin')}</Label>
                <Input
                  id="temp_min"
                  type="number"
                  value={formData.temp_min}
                  onChange={(e) => setFormData({ ...formData, temp_min: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="temp_max">{t('shipments.tempMax')}</Label>
                <Input
                  id="temp_max"
                  type="number"
                  value={formData.temp_max}
                  onChange={(e) => setFormData({ ...formData, temp_max: Number(e.target.value) })}
                  required
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="time_window_start">{t('shipments.timeWindowStart')}</Label>
                <Input
                  id="time_window_start"
                  type="time"
                  value={formData.time_window_start}
                  onChange={(e) => setFormData({ ...formData, time_window_start: e.target.value })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="time_window_end">{t('shipments.timeWindowEnd')}</Label>
                <Input
                  id="time_window_end"
                  type="time"
                  value={formData.time_window_end}
                  onChange={(e) => setFormData({ ...formData, time_window_end: e.target.value })}
                  required
                />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="service_time_minutes">{t('shipments.serviceTime')}</Label>
                <Input
                  id="service_time_minutes"
                  type="number"
                  value={formData.service_time_minutes}
                  onChange={(e) => setFormData({ ...formData, service_time_minutes: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="priority">{t('shipments.priority')}</Label>
                <Select
                  value={String(formData.priority)}
                  onValueChange={(value) => setFormData({ ...formData, priority: value })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="high">{t('shipments.priorityHigh')}</SelectItem>
                    <SelectItem value="medium">{t('shipments.priorityMedium')}</SelectItem>
                    <SelectItem value="low">{t('shipments.priorityLow')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="status">{t('shipments.status')}</Label>
                <Select
                  value={formData.status}
                  onValueChange={(value: Shipment['status']) => setFormData({ ...formData, status: value })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pending">{t('shipments.statusPending')}</SelectItem>
                    <SelectItem value="assigned">{t('shipments.statusAssigned')}</SelectItem>
                    <SelectItem value="in_transit">{t('shipments.statusInTransit')}</SelectItem>
                    <SelectItem value="delivered">{t('shipments.statusDelivered')}</SelectItem>
                    <SelectItem value="failed">{t('shipments.statusFailed')}</SelectItem>
                  </SelectContent>
                </Select>
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

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('shipments.deleteShipment')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t('shipments.confirmDelete')}</p>
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

      {/* Reset All Confirmation Dialog */}
      <Dialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('shipments.resetAllTitle')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t('shipments.confirmReset')}</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleConfirmReset} disabled={resetMutation.isPending}>
              {resetMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('shipments.resetAll')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
