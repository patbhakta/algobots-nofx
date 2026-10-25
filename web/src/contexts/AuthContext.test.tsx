import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import { LanguageProvider } from './LanguageContext'
import { getSystemConfig } from '../lib/config'

/**
 * Multi-tenant login session persistence (ALG-3342).
 *
 * A login (or registration) response carries the tenant identity
 * (tenant_id, mirroring user_id since each login = one investor tenant).
 * The persisted auth user must keep that tenant scope so the UI can always
 * attribute data to the right tenant.
 */

vi.mock('../lib/config', () => ({
  getSystemConfig: vi.fn().mockResolvedValue({ initialized: true }),
  invalidateSystemConfig: vi.fn(),
}))

vi.mock('../lib/httpClient', () => ({
  httpClient: { post: vi.fn() },
  reset401Flag: vi.fn(),
}))

const mockedGetSystemConfig = vi.mocked(getSystemConfig)

let loginProbe: ((email: string, password: string) => Promise<{
  success: boolean
  message?: string
}>) | null = null

function LoginProbe() {
  const { login } = useAuth()
  loginProbe = login
  return <div data-testid="login-probe" />
}

describe('AuthContext multi-tenant session', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    loginProbe = null
  })

  it('persists tenant_id from the login response into the auth user', async () => {
    mockedGetSystemConfig.mockResolvedValue({ initialized: true })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        token: 'tenant-token',
        user_id: 'tenant-42',
        tenant_id: 'tenant-42',
        email: 'investor@algobots.test',
        message: 'Login successful',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter>
        <LanguageProvider>
          <AuthProvider>
            <LoginProbe />
          </AuthProvider>
        </LanguageProvider>
      </MemoryRouter>
    )

    expect(loginProbe).not.toBeNull()
    const result = await loginProbe!('investor@algobots.test', 'TenantPass123!')
    expect(result.success).toBe(true)

    await waitFor(() => {
      expect(localStorage.getItem('auth_token')).toBe('tenant-token')
    })

    const savedUser = JSON.parse(localStorage.getItem('auth_user') || '{}')
    expect(savedUser).toEqual({
      id: 'tenant-42',
      email: 'investor@algobots.test',
      tenantId: 'tenant-42',
    })

    vi.unstubAllGlobals()
  })

  it('falls back to user_id as tenant scope for legacy backends without tenant_id', async () => {
    mockedGetSystemConfig.mockResolvedValue({ initialized: true })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        token: 'legacy-token',
        user_id: 'legacy-user-1',
        email: 'legacy@algobots.test',
        message: 'Login successful',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <MemoryRouter>
        <LanguageProvider>
          <AuthProvider>
            <LoginProbe />
          </AuthProvider>
        </LanguageProvider>
      </MemoryRouter>
    )

    const result = await loginProbe!('legacy@algobots.test', 'TenantPass123!')
    expect(result.success).toBe(true)

    await waitFor(() => {
      expect(localStorage.getItem('auth_token')).toBe('legacy-token')
    })
    const savedUser = JSON.parse(localStorage.getItem('auth_user') || '{}')
    expect(savedUser.tenantId).toBe('legacy-user-1')

    vi.unstubAllGlobals()
  })
})
