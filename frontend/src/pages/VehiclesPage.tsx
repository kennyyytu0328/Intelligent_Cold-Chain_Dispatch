import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Pencil, Trash2, Loader2 } from 'lucide-react'
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
import { vehicleAPI, Vehicle } from '@/services/api'

const defaultVehicle: Omit<Vehicle, 'id'> = {
  license_plate: '',
  capacity_kg: 1000,
  min_temp: -20,
  max_temp: 8,
  cooling_rate: 0.5,
  insulation_factor: 0.02,
  status: 'active',
}

export default function VehiclesPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [editingVehicle, setEditingVehicle] = useState<Vehicle | null>(null)
  const [formData, setFormData] = useState(defaultVehicle)

  const { data: vehicles = [], isLoading } = useQuery({
    queryKey: ['vehicles'],
    queryFn: vehicleAPI.getAll,
  })

  const createMutation = useMutation({
    mutationFn: vehicleAPI.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      toast.success(t('vehicles.saveSuccess'))
      setDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Vehicle> }) =>
      vehicleAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      toast.success(t('vehicles.saveSuccess'))
      setDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: vehicleAPI.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vehicles'] })
      toast.success(t('vehicles.deleteSuccess'))
      setDeleteDialogOpen(false)
    },
    onError: () => toast.error(t('common.error')),
  })

  const handleAdd = () => {
    setEditingVehicle(null)
    setFormData(defaultVehicle)
    setDialogOpen(true)
  }

  const handleEdit = (vehicle: Vehicle) => {
    setEditingVehicle(vehicle)
    setFormData({
      license_plate: vehicle.license_plate,
      capacity_kg: vehicle.capacity_kg,
      min_temp: vehicle.min_temp,
      max_temp: vehicle.max_temp,
      cooling_rate: vehicle.cooling_rate,
      insulation_factor: vehicle.insulation_factor,
      status: vehicle.status,
    })
    setDialogOpen(true)
  }

  const handleDelete = (vehicle: Vehicle) => {
    setEditingVehicle(vehicle)
    setDeleteDialogOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingVehicle) {
      updateMutation.mutate({ id: editingVehicle.id, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  const handleConfirmDelete = () => {
    if (editingVehicle) {
      deleteMutation.mutate(editingVehicle.id)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">{t('vehicles.title')}</h1>
        <Button onClick={handleAdd}>
          <Plus className="mr-2 h-4 w-4" />
          {t('vehicles.addVehicle')}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('vehicles.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : vehicles.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">{t('common.none')}</p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('vehicles.licensePlate')}</TableHead>
                    <TableHead>{t('vehicles.capacity')}</TableHead>
                    <TableHead>{t('vehicles.minTemp')}</TableHead>
                    <TableHead>{t('vehicles.maxTemp')}</TableHead>
                    <TableHead>{t('vehicles.status')}</TableHead>
                    <TableHead className="text-right">{t('common.actions')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {vehicles.map((vehicle) => (
                    <TableRow key={vehicle.id}>
                      <TableCell className="font-medium">{vehicle.license_plate}</TableCell>
                      <TableCell>{vehicle.capacity_kg} kg</TableCell>
                      <TableCell>{vehicle.min_temp}°C</TableCell>
                      <TableCell>{vehicle.max_temp}°C</TableCell>
                      <TableCell>
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                            vehicle.status === 'active'
                              ? 'bg-green-100 text-green-700'
                              : vehicle.status === 'maintenance'
                              ? 'bg-yellow-100 text-yellow-700'
                              : 'bg-gray-100 text-gray-700'
                          }`}
                        >
                          {t(`vehicles.status${vehicle.status.charAt(0).toUpperCase() + vehicle.status.slice(1)}`)}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="ghost" size="icon" onClick={() => handleEdit(vehicle)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => handleDelete(vehicle)}>
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
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editingVehicle ? t('vehicles.editVehicle') : t('vehicles.addVehicle')}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="license_plate">{t('vehicles.licensePlate')}</Label>
              <Input
                id="license_plate"
                value={formData.license_plate}
                onChange={(e) => setFormData({ ...formData, license_plate: e.target.value })}
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="capacity_kg">{t('vehicles.capacity')}</Label>
                <Input
                  id="capacity_kg"
                  type="number"
                  value={formData.capacity_kg}
                  onChange={(e) => setFormData({ ...formData, capacity_kg: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="status">{t('vehicles.status')}</Label>
                <Select
                  value={formData.status}
                  onValueChange={(value: Vehicle['status']) => setFormData({ ...formData, status: value })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">{t('vehicles.statusActive')}</SelectItem>
                    <SelectItem value="inactive">{t('vehicles.statusInactive')}</SelectItem>
                    <SelectItem value="maintenance">{t('vehicles.statusMaintenance')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="min_temp">{t('vehicles.minTemp')}</Label>
                <Input
                  id="min_temp"
                  type="number"
                  value={formData.min_temp}
                  onChange={(e) => setFormData({ ...formData, min_temp: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="max_temp">{t('vehicles.maxTemp')}</Label>
                <Input
                  id="max_temp"
                  type="number"
                  value={formData.max_temp}
                  onChange={(e) => setFormData({ ...formData, max_temp: Number(e.target.value) })}
                  required
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="cooling_rate">{t('vehicles.coolingRate')}</Label>
                <Input
                  id="cooling_rate"
                  type="number"
                  step="0.01"
                  value={formData.cooling_rate}
                  onChange={(e) => setFormData({ ...formData, cooling_rate: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="insulation_factor">{t('vehicles.insulationFactor')}</Label>
                <Input
                  id="insulation_factor"
                  type="number"
                  step="0.001"
                  value={formData.insulation_factor}
                  onChange={(e) => setFormData({ ...formData, insulation_factor: Number(e.target.value) })}
                  required
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

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('vehicles.deleteVehicle')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{t('vehicles.confirmDelete')}</p>
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
