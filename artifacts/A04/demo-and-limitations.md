# A04 demo and limitations — accounts, secrets, capability registry (ALG-3100)

## Demo (`make demo-A04`)

The demo (full output in `demo-output.txt`) runs the founder scene on a
throwaway migrated SQLite database with synthetic users only:

1. **Four mock accounts onboarded** across two environments
   (`mock:synthetic-paper` x3, `mock:development` x1) with distinct
   identities (`mock/…1a2a`-style masked fingerprints), distinct base
   currencies and `CONNECTED` sessions.
2. **One execution identity per secret** — four `SecretResolver` grants with
   canonical `secret://tenant/<tid>/account/<aid>` references, all `ACTIVE`
   at version 1.
3. **Rotation in place** — Mock beta's credential rotates to version 2 on the
   same grant row (`ROTATED`), and re-onboarding the same external account is
   rejected `409` with a generic message that names no owner.
4. **Capability preview** — an equity stop order on the mock venue is
   rejected before submission (absent rows are disabled, never assumed).
5. **Per-account status** — one line per account: registry status, broker
   session state, secret state/version, reconciliation posture.
6. **Recovery** — revoking Mock delta's grant freezes the account
   (`status=frozen`, session `EXPIRED`) and marks the connection
   `needs_reconciliation (credentials revoked)` — exposure is flagged for
   reconciliation, not shown as flat.

## What works

- Onboarding against the mock provider + candidate real provider
  configuration (`alpaca`, paper-only, sessions stay `UNCONFIGURED`).
- Broker session state separate from control-plane user authentication; the
  auth contract is untouched (tenant derives from the server-side session).
- Fernet-sealed credentials with a key-ring service (active + retired key
  ids) so master-key rotation never orphans blobs; no plaintext credential in
  any response, log, exception or audit row (assert-tested).
- Resolution ACL: only the assigned execution identity, in the owning tenant,
  in an allowed environment, to an allowlisted egress host, with a healthy
  token — denials audited with ids and reasons only.
- Rotation bumps the version in place; no second account/identity/grant row
  ever appears (AC5).
- Capability registry per (provider, environment) as a registered schema
  version (`BrokerAdapterCapabilities@1.0`), default-deny for unknown
  product/order-type pairs.
- Duplicate external-account detection via a globally unique fingerprint
  index (PostgreSQL-proven) with an owner-blind 409.
- PostgreSQL FORCE RLS on the three new tables, same policy family as A03.

## Limitations and follow-ups

1. **PostgreSQL evidence is local, not CI** (same as A03 limitation 1): the
   RLS and fingerprint-index cases need `ALGOBOTS_A04_PG_ADMIN_URL` and skip
   as BLOCKED in CI. A `postgres:16` service is the workflow owner's call.
2. **Resolution is in-process.** Workers in the paper core share the API
   process, so the ACL boundary is `SecretStore.resolve`, not an HTTP route
   — there is deliberately no endpoint that returns secret material. When
   workers become separate services (A06+), the resolution call needs an
   authenticated service-identity transport; the grant rows already carry
   `assigned_principal_id` for that.
3. **Candidate provider is configuration-only.** Activating real Alpaca
   sessions (or any live environment) is a later packet with separate
   authorization; A04 rejects `live` at onboarding and grant time.
4. **Ownership transfer is not implemented** — duplicate external accounts
   get a reviewed-workflow pointer (`ownership_epoch` exists on the identity
   row, nothing moves it yet).
5. **Rotation of the credential master key** is supported mechanically
   (retired key ids in the ring) but no scheduled job performs it; the sweep
   only refreshes broker tokens.
6. **Principal registry.** `assigned_principal_id` values are opaque
   identifiers validated for shape, not yet backed by a principals table;
   A06's worker identities should issue them.

## Excluded environments

development + synthetic-paper only. No payment processor merchant accounts,
no real trading, no live capital.
