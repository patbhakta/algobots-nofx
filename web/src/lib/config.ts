export interface SystemConfig {
  initialized: boolean
  beta_mode?: boolean
  /**
   * Backend-controlled registration gate (multi-tenant login). True while the
   * system is uninitialized (first tenant bootstrap) or while the operator has
   * registration open (`algobots set-registration --enable`). When false the
   * register page shows the registration-closed screen.
   */
  registration_enabled?: boolean
}

let configPromise: Promise<SystemConfig> | null = null
let cachedConfig: SystemConfig | null = null

export function getSystemConfig(): Promise<SystemConfig> {
  if (cachedConfig) {
    return Promise.resolve(cachedConfig)
  }
  if (configPromise) {
    return configPromise
  }
  configPromise = fetch('/api/config')
    .then((res) => res.json())
    .then((data: SystemConfig) => {
      cachedConfig = data
      return data
    })
  return configPromise
}

/** Call after first-time setup completes so next check reflects initialized=true */
export function invalidateSystemConfig() {
  cachedConfig = null
  configPromise = null
  window.dispatchEvent(new Event('system-config-invalidated'))
}
