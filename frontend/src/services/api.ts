import axios, { AxiosError } from 'axios'
import { useAuthStore } from '@/stores/authStore'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor to handle errors
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Don't redirect if this is a login attempt failure
      const isLoginEndpoint = error.config?.url?.includes('/auth/token')

      if (!isLoginEndpoint) {
        // Only logout and redirect for authenticated requests that fail
        useAuthStore.getState().logout()
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api

// Auth API
export const authAPI = {
  login: async (username: string, password: string) => {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)
    const response = await api.post('/auth/token', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },
}

// Vehicle API - matches backend VehicleResponse schema
export interface VehicleAPI {
  id: string
  license_plate: string
  capacity_weight: string
  capacity_volume: string
  insulation_grade: string
  k_value: string
  door_type: string
  door_coefficient: string
  has_strip_curtains: boolean
  cooling_rate: string
  min_temp_capability: string
  status: string
  created_at: string
  updated_at: string
}

// Frontend-friendly interface
export interface Vehicle {
  id: string
  license_plate: string
  capacity_kg: number
  min_temp: number
  max_temp: number
  cooling_rate: number
  insulation_factor: number
  status: string
}

// Transform API response to frontend format
const mapVehicleFromAPI = (v: VehicleAPI): Vehicle => ({
  id: v.id,
  license_plate: v.license_plate,
  capacity_kg: Number(v.capacity_weight),
  min_temp: Number(v.min_temp_capability),
  max_temp: 8, // Default max temp (not in API)
  cooling_rate: Math.abs(Number(v.cooling_rate)),
  insulation_factor: Number(v.k_value),
  status: v.status.toLowerCase(),
})

// Transform frontend data to API format for create/update
const mapVehicleToAPI = (v: Omit<Vehicle, 'id'>): Record<string, unknown> => ({
  license_plate: v.license_plate,
  capacity_weight: v.capacity_kg,
  capacity_volume: v.capacity_kg / 200, // Estimate volume from weight
  cooling_rate: -Math.abs(v.cooling_rate), // API expects negative
  min_temp_capability: v.min_temp,
  status: v.status.toUpperCase(),
})

export const vehicleAPI = {
  getAll: async () => {
    const response = await api.get<{ items: VehicleAPI[]; total: number }>('/vehicles')
    return (response.data.items || []).map(mapVehicleFromAPI)
  },
  getById: async (id: string) => {
    const response = await api.get<VehicleAPI>(`/vehicles/${id}`)
    return mapVehicleFromAPI(response.data)
  },
  create: async (data: Omit<Vehicle, 'id'>) => {
    const response = await api.post<VehicleAPI>('/vehicles', mapVehicleToAPI(data))
    return mapVehicleFromAPI(response.data)
  },
  update: async (id: string, data: Partial<Vehicle>) => {
    const response = await api.patch<VehicleAPI>(`/vehicles/${id}`, mapVehicleToAPI(data as Omit<Vehicle, 'id'>))
    return mapVehicleFromAPI(response.data)
  },
  delete: async (id: string) => {
    await api.delete(`/vehicles/${id}`)
  },
}

// Shipment API - matches backend ShipmentResponse schema
export interface ShipmentAPI {
  id: string
  order_number: string
  customer_id: string
  delivery_address: string
  latitude: string
  longitude: string
  weight: string
  volume: string
  temp_limit_upper: string | null
  temp_limit_lower: string | null
  time_windows: Array<{ start: string; end: string }>
  service_duration: number
  priority: number
  status: string
  sla_tier: string
  created_at: string
  updated_at: string
}

// Frontend-friendly interface
export interface Shipment {
  id: string
  customer_name: string
  address: string
  latitude: number
  longitude: number
  weight_kg: number
  temp_min: number
  temp_max: number
  time_window_start: string
  time_window_end: string
  service_time_minutes: number
  priority: number | string
  status: string
}

// Transform API response to frontend format
const mapShipmentFromAPI = (s: ShipmentAPI): Shipment => ({
  id: s.id,
  customer_name: s.order_number, // Use order_number as display name
  address: s.delivery_address,
  latitude: Number(s.latitude),
  longitude: Number(s.longitude),
  weight_kg: Number(s.weight),
  temp_min: s.temp_limit_lower ? Number(s.temp_limit_lower) : 0,
  temp_max: s.temp_limit_upper ? Number(s.temp_limit_upper) : 8,
  time_window_start: s.time_windows?.[0]?.start || '08:00',
  time_window_end: s.time_windows?.[0]?.end || '18:00',
  service_time_minutes: s.service_duration,
  priority: s.priority,
  status: s.status?.toLowerCase() || 'pending', // Normalize to lowercase
})

// Transform frontend shipment data to API format for updates
const mapShipmentToAPI = (data: Partial<Shipment>): Record<string, unknown> => {
  const mapped: Record<string, unknown> = {}
  if (data.address !== undefined) mapped.delivery_address = data.address
  if (data.latitude !== undefined) mapped.latitude = data.latitude
  if (data.longitude !== undefined) mapped.longitude = data.longitude
  if (data.weight_kg !== undefined) mapped.weight = data.weight_kg
  if (data.temp_min !== undefined) mapped.temp_limit_lower = data.temp_min
  if (data.temp_max !== undefined) mapped.temp_limit_upper = data.temp_max
  if (data.service_time_minutes !== undefined) mapped.service_duration = data.service_time_minutes
  if (data.priority !== undefined) mapped.priority = data.priority
  if (data.status !== undefined) mapped.status = data.status.toUpperCase()
  // Map time windows - backend expects array of {start, end} objects
  if (data.time_window_start !== undefined && data.time_window_end !== undefined) {
    mapped.time_windows = [{ start: data.time_window_start, end: data.time_window_end }]
  }
  return mapped
}

export const shipmentAPI = {
  getAll: async () => {
    const response = await api.get<{ items: ShipmentAPI[]; total: number }>('/shipments')
    return (response.data.items || []).map(mapShipmentFromAPI)
  },
  getById: async (id: string) => {
    const response = await api.get<Shipment>(`/shipments/${id}`)
    return response.data
  },
  create: async (data: Omit<Shipment, 'id'>) => {
    const response = await api.post<Shipment>('/shipments', data)
    return response.data
  },
  update: async (id: string, data: Partial<Shipment>) => {
    const response = await api.patch<ShipmentAPI>(`/shipments/${id}`, mapShipmentToAPI(data))
    return mapShipmentFromAPI(response.data)
  },
  delete: async (id: string) => {
    await api.delete(`/shipments/${id}`)
  },
  resetAll: async () => {
    const response = await api.post<{ message: string; shipments_reset: number }>('/shipments/reset')
    return response.data
  },
}

// Depot API
export interface Depot {
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

export const depotAPI = {
  getAll: async () => {
    const response = await api.get<{ total: number; depots: Depot[] }>('/depots')
    return response.data
  },
  getById: async (id: string) => {
    const response = await api.get<Depot>(`/depots/${id}`)
    return response.data
  },
}

// Optimization API
export interface OptimizationParams {
  plan_date: string  // YYYY-MM-DD format
  planned_departure_time: string  // HH:MM format
  depot_lat: number
  depot_lon: number
  ambient_temp: number
  initial_cargo_temp: number
  max_iterations?: number
}

export interface OptimizationTask {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  result?: unknown
  error?: string
}

// Transform frontend params to backend API format
const mapOptimizationToAPI = (params: OptimizationParams) => ({
  plan_date: params.plan_date,
  planned_departure_time: params.planned_departure_time,
  depot_latitude: params.depot_lat,
  depot_longitude: params.depot_lon,
  parameters: {
    ambient_temperature: params.ambient_temp,
    initial_vehicle_temp: params.initial_cargo_temp,
    time_limit_seconds: params.max_iterations || 300,
  },
})

export interface ViolationReason {
  type: 'TIME_WINDOW' | 'STRICT_SLA' | 'TEMPERATURE' | 'CAPACITY_OR_ROUTING'
  message: string
  parameter: string
  current_value: string
  constraint_value: string
}

export interface ViolationInfo {
  temperature_violations: Array<{
    order_number: string
    address: string
    sequence: number
    predicted_temp: number
    temp_limit: number
    violation_amount: number
    sla_tier: string
  }>
  unassigned_shipments: Array<{
    order_number: string
    address: string
    time_windows: string
    temp_limit: number
    sla_tier: string
    weight_kg: number
    likely_reasons: ViolationReason[]
  }>
  summary: {
    total_temp_violations: number
    total_unassigned: number
  }
}

export const optimizationAPI = {
  start: async (params: OptimizationParams) => {
    const response = await api.post<{ job_id: string }>('/optimization', mapOptimizationToAPI(params))
    return { task_id: response.data.job_id }
  },
  getStatus: async (taskId: string, _timeLimitSeconds: number = 200) => {
    const response = await api.get<{
      job_id: string
      status: string
      progress: number
      created_at: string
      started_at?: string
      result_summary?: {
        total_distance_km: string
        total_duration_minutes: number
        routes_created: number
      }
      error_message?: string
    }>(`/optimization/${taskId}`)

    const data = response.data
    const statusMap: Record<string, OptimizationTask['status']> = {
      'PENDING': 'pending',
      'RUNNING': 'running',
      'COMPLETED': 'completed',
      'FAILED': 'failed',
    }

    // Use progress from backend directly
    let progress = data.progress || 0
    if (data.status === 'COMPLETED') {
      progress = 100
    } else if (data.status === 'PENDING') {
      progress = 2
    }

    return {
      task_id: data.job_id,
      status: statusMap[data.status] || 'pending',
      progress,
      error: data.error_message,
    } as OptimizationTask
  },
  getResult: async (taskId: string) => {
    const response = await api.get<{
      result_summary?: {
        total_distance_km: string
        total_duration_minutes: number
        routes_created: number
        shipments_unassigned: number
      }
    }>(`/optimization/${taskId}`)

    const summary = response.data.result_summary
    return {
      totalDistance: summary ? Number(summary.total_distance_km) : 0,
      totalTime: summary?.total_duration_minutes || 0,
      routeCount: summary?.routes_created || 0,
      shipmentsUnassigned: summary?.shipments_unassigned || 0,
    }
  },

  getViolations: async (taskId: string): Promise<ViolationInfo> => {
    const response = await api.get<ViolationInfo>(`/optimization/${taskId}/violations`)
    return response.data
  },
}

// Routes API
export interface MapRouteStop {
  sequence: number
  shipmentId: string
  customerName: string
  address: string
  lat: number
  lon: number
  arrivalTime: string
  departureTime: string
  temperature: number
  tempLimit: number
  feasible: boolean
}

export interface MapRoute {
  vehicleId: string
  licensePlate: string
  color: string
  totalDistance: number
  totalTime: number
  stops: MapRouteStop[]
}

export interface MapRoutesResponse {
  routes: MapRoute[]
  depot: { lat: number; lon: number } | null
}

export const routesAPI = {
  getForMap: async (planDate: string, jobId?: string): Promise<MapRoutesResponse> => {
    const params = new URLSearchParams({ plan_date: planDate })
    if (jobId) {
      params.append('job_id', jobId)
    }
    const response = await api.get<MapRoutesResponse>(`/routes/map-data?${params}`)
    return response.data
  },
}

// Excel Import API
export const excelAPI = {
  importVehicles: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post('/import/vehicles', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },
  importShipments: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post('/import/shipments', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },
  downloadVehicleTemplate: () => {
    return `${api.defaults.baseURL}/import/template/vehicles`
  },
  downloadShipmentTemplate: () => {
    return `${api.defaults.baseURL}/import/template/shipments`
  },
}
