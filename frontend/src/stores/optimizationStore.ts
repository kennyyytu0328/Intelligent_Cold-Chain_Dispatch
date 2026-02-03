import { create } from 'zustand'
import { ViolationInfo } from '@/services/api'

export interface OptimizationResult {
  taskId: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  routes: RouteResult[]
  totalDistance: number
  totalTime: number
  feasible: boolean
  message?: string
  depot?: { lat: number; lon: number }
}

export interface RouteResult {
  vehicleId: string
  licensePlate: string
  color: string
  stops: RouteStop[]
  totalDistance: number
  totalTime: number
}

export interface RouteStop {
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

interface OptimizationState {
  currentResult: OptimizationResult | null
  violations: ViolationInfo | null
  isOptimizing: boolean
  setResult: (result: OptimizationResult | null) => void
  setViolations: (violations: ViolationInfo | null) => void
  setOptimizing: (optimizing: boolean) => void
  updateProgress: (progress: number) => void
  reset: () => void
}

export const useOptimizationStore = create<OptimizationState>((set) => ({
  currentResult: null,
  violations: null,
  isOptimizing: false,
  setResult: (result) => set({ currentResult: result }),
  setViolations: (violations) => set({ violations }),
  setOptimizing: (optimizing) => set({ isOptimizing: optimizing }),
  updateProgress: (progress) =>
    set((state) => ({
      currentResult: state.currentResult
        ? { ...state.currentResult, progress }
        : null,
    })),
  reset: () => set({ currentResult: null, violations: null, isOptimizing: false }),
}))
