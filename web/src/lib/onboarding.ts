export type UserMode = 'beginner' | 'advanced'

const USER_MODE_KEY = 'nofx_user_mode'
const BEGINNER_WALLET_ADDRESS_KEY = 'nofx_beginner_wallet_address'
const BEGINNER_ONBOARDING_COMPLETED_KEY = 'nofx_beginner_onboarding_completed'

export function getUserMode(): UserMode | null {
  const value = localStorage.getItem(USER_MODE_KEY)
  if (value === 'beginner' || value === 'advanced') {
    return value
  }
  return null
}

export function setUserMode(mode: UserMode) {
  localStorage.setItem(USER_MODE_KEY, mode)
}

export function getPostAuthPath(_mode: UserMode | null | undefined): string {
  // The live paper-loop dashboard is the first screen for every invited user.
  return '/dashboard'
}

export function setBeginnerWalletAddress(address: string) {
  localStorage.setItem(BEGINNER_WALLET_ADDRESS_KEY, address)
}

export function getBeginnerWalletAddress(): string | null {
  return localStorage.getItem(BEGINNER_WALLET_ADDRESS_KEY)
}

export function hasCompletedBeginnerOnboarding(): boolean {
  return localStorage.getItem(BEGINNER_ONBOARDING_COMPLETED_KEY) === 'true'
}

export function markBeginnerOnboardingCompleted() {
  localStorage.setItem(BEGINNER_ONBOARDING_COMPLETED_KEY, 'true')
}
