import { describe, it, expect, beforeEach } from 'vitest'
import { useOptimizationStore, OptimizationResult } from './optimizationStore'

const makeResult = (overrides?: Partial<OptimizationResult>): OptimizationResult => ({
  taskId: 'task-1',
  status: 'completed',
  progress: 100,
  routes: [],
  totalDistance: 50,
  totalTime: 120,
  feasible: true,
  ...overrides,
})

describe('optimizationStore', () => {
  beforeEach(() => {
    useOptimizationStore.setState({
      currentResult: null,
      violations: null,
      isOptimizing: false,
    })
  })

  it('starts with null result, null violations, not optimizing', () => {
    const state = useOptimizationStore.getState()
    expect(state.currentResult).toBeNull()
    expect(state.violations).toBeNull()
    expect(state.isOptimizing).toBe(false)
  })

  it('setOptimizing updates isOptimizing flag', () => {
    useOptimizationStore.getState().setOptimizing(true)
    expect(useOptimizationStore.getState().isOptimizing).toBe(true)

    useOptimizationStore.getState().setOptimizing(false)
    expect(useOptimizationStore.getState().isOptimizing).toBe(false)
  })

  it('setResult stores the optimization result', () => {
    const result = makeResult()
    useOptimizationStore.getState().setResult(result)

    expect(useOptimizationStore.getState().currentResult).toEqual(result)
  })

  it('updateProgress creates a new result object (immutability)', () => {
    const result = makeResult({ progress: 50 })
    useOptimizationStore.getState().setResult(result)

    useOptimizationStore.getState().updateProgress(75)

    const updated = useOptimizationStore.getState().currentResult
    expect(updated).not.toBeNull()
    expect(updated!.progress).toBe(75)
    // Immutability: original object should not be mutated
    expect(result.progress).toBe(50)
    // New object reference
    expect(updated).not.toBe(result)
  })

  it('updateProgress does nothing when currentResult is null', () => {
    useOptimizationStore.getState().updateProgress(50)
    expect(useOptimizationStore.getState().currentResult).toBeNull()
  })

  it('reset clears all state', () => {
    useOptimizationStore.getState().setResult(makeResult())
    useOptimizationStore.getState().setOptimizing(true)

    useOptimizationStore.getState().reset()

    const state = useOptimizationStore.getState()
    expect(state.currentResult).toBeNull()
    expect(state.violations).toBeNull()
    expect(state.isOptimizing).toBe(false)
  })
})
