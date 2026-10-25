/**
 * The built-in AI provider's **wire identifier** — a protocol token, not copy.
 *
 * The Go backend assigns this value server-side and the frontend only ever
 * reads it: `api/handler_ai_model.go` seeds the catalog with
 * `{ID: "claw402", Provider: "claw402"}`, `api/handler_onboarding.go` writes
 * the same for beginner onboarding, and `store/ai_charge.go` /
 * `api/launch_preflight.go` gate on the literal. The matching status field is
 * `claw402_status` (`api/handler_wallet.go`).
 *
 * ALG-3355 substituted the token for a display word across `web/` without
 * touching the 383 Go references, so every read-path comparison silently
 * stopped matching (ALG-3367): the dedicated wallet form never rendered, the
 * provider-config lookups returned `undefined`, the status indicator was
 * permanently unknown, and launch could bind an Autopilot to the member's own
 * API key instead of the built-in model.
 *
 * Compare against this constant instead of inlining a word. Display names live
 * in `AI_PROVIDER_CONFIG[...].apiName` and the i18n strings, so a rebrand sweep
 * can rewrite what members see without reaching the wire again.
 *
 * Renaming the wire value itself needs the Go rename plus a migration for
 * persisted `ai_models.provider` rows — and `.243:8200` still runs the
 * *upstream* backend image, not a fork build, so it stays `claw402` until the
 * fork ships its own backend.
 */
export const AI_PROVIDER_ID = 'claw402'

/** The status field the backend returns from `POST /api/wallet/validate`. */
export const AI_PROVIDER_STATUS_FIELD = 'claw402_status'

/**
 * True when this model is the built-in provider.
 *
 * Both fields are checked because the backend uses the same value for the
 * catalog id and the provider, and a persisted row can carry either.
 */
export function isBuiltInProvider(
  model: { id?: string; provider?: string } | null | undefined
): boolean {
  if (!model) return false
  return model.provider === AI_PROVIDER_ID || model.id === AI_PROVIDER_ID
}
