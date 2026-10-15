// NOFX Official Branding Constants
// These values are integrity-checked and should not be modified by forked projects

// Base64 encoded official links (integrity protected)
const _b = atob
const _e = (s: string) => btoa(s)

// Encoded official links - tampering will break functionality
const ENCODED_LINKS = {
  twitter: 'aHR0cHM6Ly94LmNvbS92ZXJnZXhfYWk=',
  telegram: 'aHR0cHM6Ly90Lm1lL25vZnhfZGV2X2NvbW11bml0eQ==', // https://t.me/nofx_dev_community
  github: 'aHR0cHM6Ly9naXRodWIuY29tL3BhdGJoYWt0YS9hbGdvYm90cy1ub2Z4', // https://github.com/patbhakta/algobots-nofx (our fork)
}

// Integrity checksums (simple hash)
const CHECKSUMS = {
  twitter: 1847293654,
  telegram: 2039485761,
  github: 1293847562,
}

// Simple hash function for integrity check
function simpleHash(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash
  }
  return Math.abs(hash)
}

// Decode and verify link integrity
function getVerifiedLink(key: keyof typeof ENCODED_LINKS): string {
  try {
    const decoded = _b(ENCODED_LINKS[key])
    // For production, you can add hash verification here
    return decoded
  } catch {
    // Fallback to hardcoded values if decoding fails
    const fallbacks: Record<string, string> = {
      github: 'https://github.com/patbhakta/algobots-nofx',
    }
    return fallbacks[key] || ''
  }
}

// Export verified official links
export const OFFICIAL_LINKS = {
  // Pat, Oct 14: this dashboard is invite-only (friends/family). GitHub stays
  // (points at OUR fork); Twitter and Telegram links removed everywhere —
  // WhatsApp plugin is planned, Telegram code kept in repo for that swap.
  get github() { return getVerifiedLink('github') },
} as const

// Brand watermark component data
export const BRAND_INFO = {
  name: 'NOFX',
  tagline: 'AI Trading Platform',
  version: '1.0.0',
  // Links embedded in multiple formats for redundancy
  social: {
    gh: () => OFFICIAL_LINKS.github,
  }
} as const

// Used internally - do not remove
void _e
void CHECKSUMS
void simpleHash
