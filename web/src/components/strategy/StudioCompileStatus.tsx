// ALG-3415: render the AlgoBots /api/studio compile result that every NoFX
// strategy save now carries (`strategy.studio`, added by ALG-3408).
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { StudioCompileStatus } from '../../types'

// Editor sections and the compile-error field paths each one owns. Paths are
// either the NoFX config path (coin_source.static_coins) or the Studio draft
// path the translation produced (universe.symbols.0).
export const STUDIO_FIELD_OWNERS = {
  name: ['name'],
  universe: ['coin_source', 'universe'],
  candles: ['indicators', 'signals'],
  params: ['risk_control', 'risk', 'baseline'],
  note: [
    'custom_prompt',
    'prompt_sections',
    'decision.mode',
    'decision.custom_prompt',
  ],
} as const

export type StudioFieldOwner = keyof typeof STUDIO_FIELD_OWNERS

function ownsField(owner: StudioFieldOwner, field: string) {
  return STUDIO_FIELD_OWNERS[owner].some(
    (prefix) => field === prefix || field.startsWith(`${prefix}.`)
  )
}

function shortHash(hash?: string) {
  return hash ? hash.slice(0, 12) : ''
}

export function StudioStatusBadge({
  studio,
}: {
  studio?: StudioCompileStatus | null
}) {
  if (!studio) {
    return (
      <span
        data-testid="studio-status-badge"
        className="rounded bg-nofx-bg-deeper px-1.5 py-0.5 text-[10px] text-nofx-text-muted"
      >
        not compiled
      </span>
    )
  }
  const ok = studio.status === 'compiled'
  return (
    <span
      data-testid="studio-status-badge"
      data-status={studio.status}
      title={ok ? studio.artifact_hash : `${studio.field}: ${studio.message}`}
      className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
        ok
          ? 'bg-nofx-success/15 text-nofx-success'
          : 'bg-nofx-danger/15 text-nofx-danger'
      }`}
    >
      {ok
        ? `compiled ${shortHash(studio.artifact_hash).slice(0, 7)}`
        : 'invalid'}
    </span>
  )
}

export function StudioCompilePanel({
  studio,
  stale,
}: {
  studio?: StudioCompileStatus | null
  stale: boolean
}) {
  const ok = studio?.status === 'compiled'
  return (
    <div
      data-testid="studio-compile-panel"
      data-status={studio?.status || 'none'}
      className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
        !studio
          ? 'border-[rgba(26,24,19,0.14)] bg-nofx-bg-deeper text-nofx-text-muted'
          : ok
            ? 'border-nofx-success/30 bg-nofx-success/10 text-nofx-text'
            : 'border-nofx-danger/30 bg-nofx-danger/10 text-nofx-text'
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="inline-flex items-center gap-1.5 font-semibold">
          {ok ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-nofx-success" />
          ) : (
            <AlertTriangle
              className={`h-3.5 w-3.5 ${studio ? 'text-nofx-danger' : ''}`}
            />
          )}
          Studio compile: {studio ? studio.status : 'not compiled yet'}
        </span>
        {ok ? (
          <>
            <span>
              implementation{' '}
              <code data-testid="studio-implementation">
                {studio.implementation}
              </code>
            </span>
            <span title={studio.artifact_hash}>
              artifact{' '}
              <code data-testid="studio-artifact-hash">
                {shortHash(studio.artifact_hash)}
              </code>
            </span>
            {studio.revision != null ? (
              <span>rev {studio.revision}</span>
            ) : null}
            <span>{studio.deployable ? 'deployable' : 'not deployable'}</span>
          </>
        ) : null}
        {stale ? (
          <span className="text-nofx-gold">
            unsaved edits; save to recompile
          </span>
        ) : null}
      </div>
      {studio && !ok ? (
        <div className="mt-1">
          <code data-testid="studio-error-field">{studio.field}</code>:{' '}
          <span data-testid="studio-error-message">{studio.message}</span>
        </div>
      ) : null}
      {!studio ? (
        <div className="mt-1">
          Saved before the AlgoBots Studio contract existed; save to compile it.
        </div>
      ) : null}
      {ok && studio.warnings && studio.warnings.length > 0 ? (
        <ul className="mt-1 list-disc pl-4 text-nofx-text-muted">
          {studio.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export function StudioFieldError({
  studio,
  owner,
}: {
  studio?: StudioCompileStatus | null
  owner: StudioFieldOwner
}) {
  if (studio?.status !== 'invalid' || !studio.field) return null
  if (!ownsField(owner, studio.field)) return null
  return (
    <div
      role="alert"
      data-testid={`studio-field-error-${owner}`}
      data-field={studio.field}
      className="mt-2 flex items-start gap-1.5 rounded-md border border-nofx-danger/30 bg-nofx-danger/10 px-2 py-1.5 text-xs text-nofx-danger"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>
        <code>{studio.field}</code>: {studio.message}
      </span>
    </div>
  )
}
