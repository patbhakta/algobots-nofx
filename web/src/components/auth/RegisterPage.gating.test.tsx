import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RegisterPage } from './RegisterPage'
import { getSystemConfig } from '../../lib/config'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    register: vi.fn().mockResolvedValue({ success: false, message: 'not called' }),
  }),
}))

vi.mock('../../contexts/LanguageContext', async () => {
  const actual = await vi.importActual('../../contexts/LanguageContext')
  return {
    ...actual,
    useLanguage: () => ({ language: 'en' }),
  }
})

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

vi.mock('../../lib/config', () => ({
  getSystemConfig: vi.fn(),
  invalidateSystemConfig: vi.fn(),
}))

const mockedGetSystemConfig = vi.mocked(getSystemConfig)

function renderPage() {
  return render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.location.hash = ""
})

describe('RegisterPage tenant-registration gating', () => {
  it('shows the registration-closed page when the backend toggle is off on an initialized system', async () => {
    mockedGetSystemConfig.mockResolvedValue({
      initialized: true,
      registration_enabled: false,
    })

    renderPage()

    expect(await screen.findByText('Registration Closed')).toBeTruthy()
    expect(
      screen.getByText(/User registration is currently disabled/i)
    ).toBeTruthy()
    // The registration form must not be offered at all.
    expect(screen.queryByPlaceholderText('user@algobots.os')).toBeNull()
  })

  it('shows the form from an invite link even with the backend toggle off', async () => {
    window.location.hash = '#invite=test-token'
    mockedGetSystemConfig.mockResolvedValue({
      initialized: true,
      registration_enabled: false,
    })

    renderPage()

    expect(
      await screen.findByPlaceholderText('user@algobots.os')
    ).toBeTruthy()
    expect(screen.queryByText('Registration Closed')).toBeNull()
  })

  it('stays closed on an uninitialized system even with the legacy toggle on', async () => {
    mockedGetSystemConfig.mockResolvedValue({
      initialized: false,
      registration_enabled: true,
    })

    renderPage()

    expect(await screen.findByText('Registration Closed')).toBeTruthy()
  })

  it('treats a legacy backend without the field as closed once initialized', async () => {
    mockedGetSystemConfig.mockResolvedValue({ initialized: true })

    renderPage()

    expect(await screen.findByText('Registration Closed')).toBeTruthy()
  })
})
