import { describe, expect, it } from 'vitest'
import { normalizeInviteCode } from './inviteCode'

describe('normalizeInviteCode', () => {
  it('keeps a gate-minted code verbatim (case, dashes, underscores)', () => {
    const code = 'ALG-aB3_dE-9fGhIjKlMnOpQrStU'
    expect(normalizeInviteCode(code)).toBe(code)
  })

  it('drops whitespace picked up when pasting', () => {
    expect(normalizeInviteCode('  ALG-abc_DEF\n')).toBe('ALG-abc_DEF')
  })
})
