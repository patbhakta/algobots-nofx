import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  StudioCompilePanel,
  StudioFieldError,
  StudioStatusBadge,
} from './StudioCompileStatus'

const HASH = 'a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9'

describe('Studio compile status (ALG-3415)', () => {
  it('shows a compiled artifact hash and implementation', () => {
    render(
      <StudioCompilePanel
        stale={false}
        studio={{
          status: 'compiled',
          artifact_hash: HASH,
          implementation: 'kalshi_momentum.v1',
          revision: 2,
          deployable: false,
          warnings: [],
        }}
      />
    )
    expect(screen.getByTestId('studio-artifact-hash').textContent).toBe(
      HASH.slice(0, 12)
    )
    expect(screen.getByTestId('studio-implementation').textContent).toBe(
      'kalshi_momentum.v1'
    )
  })

  it('puts an invalid field error only at the section that owns it', () => {
    const studio = {
      status: 'invalid' as const,
      field: 'coin_source.source_type',
      message: 'only a static symbol list is supported',
    }
    render(
      <>
        <StudioFieldError studio={studio} owner="universe" />
        <StudioFieldError studio={studio} owner="candles" />
        <StudioFieldError studio={studio} owner="params" />
      </>
    )
    expect(screen.getAllByRole('alert')).toHaveLength(1)
    expect(
      screen.getByTestId('studio-field-error-universe').textContent
    ).toContain('only a static symbol list is supported')
  })

  it('maps translated draft paths to their editor section', () => {
    render(
      <StudioFieldError
        owner="candles"
        studio={{
          status: 'invalid',
          field: 'indicators.klines.primary_timeframe',
          message: 'unsupported cadence 4h',
        }}
      />
    )
    expect(screen.getByRole('alert').textContent).toContain('4h')
  })

  it('does not treat a prefix-sharing field as owned', () => {
    const { container } = render(
      <StudioFieldError
        owner="name"
        studio={{ status: 'invalid', field: 'names', message: 'x' }}
      />
    )
    expect(container.textContent).toBe('')
  })

  it('labels rows saved before the Studio contract', () => {
    render(<StudioStatusBadge studio={undefined} />)
    expect(screen.getByTestId('studio-status-badge').textContent).toBe(
      'not compiled'
    )
  })
})
