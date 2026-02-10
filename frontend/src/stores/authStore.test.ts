import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from './authStore'

describe('authStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useAuthStore.setState({
      user: null,
      token: null,
      isAuthenticated: false,
    })
  })

  it('starts unauthenticated with null user and token', () => {
    const state = useAuthStore.getState()
    expect(state.user).toBeNull()
    expect(state.token).toBeNull()
    expect(state.isAuthenticated).toBe(false)
  })

  it('login sets user, token, and isAuthenticated', () => {
    useAuthStore.getState().login('admin', 'jwt-token-123')

    const state = useAuthStore.getState()
    expect(state.user).toEqual({ username: 'admin' })
    expect(state.token).toBe('jwt-token-123')
    expect(state.isAuthenticated).toBe(true)
  })

  it('logout clears user, token, and isAuthenticated', () => {
    // First login
    useAuthStore.getState().login('admin', 'jwt-token-123')
    expect(useAuthStore.getState().isAuthenticated).toBe(true)

    // Then logout
    useAuthStore.getState().logout()

    const state = useAuthStore.getState()
    expect(state.user).toBeNull()
    expect(state.token).toBeNull()
    expect(state.isAuthenticated).toBe(false)
  })
})
