import { fireEvent, render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { BaselineParameterEditor } from './BaselineParameterEditor'

describe('baseline parameters', () => {
  it('edits coin timing without losing the saved risk binding', () => {
    const onChange = vi.fn()
    render(
      <BaselineParameterEditor
        config={{
          baseline: {
            strategy: 'coin',
            entry_delay_seconds: 0,
            stake: '10.00',
          },
          demo_worker: { max_order_value: '5.00' },
        }}
        onChange={onChange}
      />
    )
    fireEvent.change(
      screen.getByLabelText('Entry delay after market open (seconds)'),
      { target: { value: '120' } }
    )
    expect(onChange).toHaveBeenCalledWith({
      baseline: { strategy: 'coin', entry_delay_seconds: 120, stake: '10.00' },
      demo_worker: { max_order_value: '5.00' },
    })
  })
  it('migrates a legacy Laya edge into editable typed parameters', () => {
    const onChange = vi.fn()
    render(
      <BaselineParameterEditor
        config={{ demo_worker: { min_edge: 0.02 } }}
        onChange={onChange}
      />
    )
    fireEvent.change(screen.getByLabelText('Minimum edge from 50% (0–0.5)'), {
      target: { value: '0.15' },
    })
    expect(onChange.mock.calls[0][0].baseline).toEqual({
      strategy: 'laya',
      min_edge: 0.15,
    })
  })
  it('exposes Jev confidence and its missing-call rule', () => {
    render(
      <BaselineParameterEditor
        config={{ baseline: { strategy: 'jev', min_confidence: 0.8 } }}
        onChange={() => {}}
      />
    )
    expect(
      screen.getByLabelText('Minimum recorded confidence (0–1)')
    ).toHaveValue(0.8)
    expect(screen.getByText(/No inference calls are made/)).toBeTruthy()
  })
})
