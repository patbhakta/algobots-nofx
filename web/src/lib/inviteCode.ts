/**
 * ALG-3414: invite codes are minted by the AlgoBots A03 gate (`ALG-` + 24
 * url-safe chars, case sensitive). Keep them verbatim — the upstream form
 * lowercased and stripped them to six alphanumerics, which made every real
 * invite unredeemable. Only whitespace from a copy/paste is dropped.
 */
export function normalizeInviteCode(raw: string): string {
  return raw.replace(/\s+/g, '')
}
