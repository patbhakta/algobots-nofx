# Account Registry (S4.1 — ALG-3090)

Multi-account-per-user-per-broker registry with encrypted credentials at rest,
per-account paper/live mode, and a silent-refresh-or-expire token-health sweep.

## Registry shape

- A user may register any number of accounts per broker (`accounts` has no
  uniqueness on `(user_id, broker)`); `label` is the per-user unique handle
  (`uq_accounts_user_label`, migration `0002`). Duplicate labels → `409`.
- `mode` (`paper` | `live`) is per account and flips independently via
  `PATCH /api/accounts/{id}`.
- All routes are tenant-scoped: another user's rows are indistinguishable from
  missing rows (`404`). Deleting an account deletes its stored credentials.

## Encrypted credentials at rest

- `PUT /api/accounts/{id}/credentials` with `{api_key, api_secret, token?,
  token_expires_at?}` seals the payload with Fernet (AES-128-CBC +
  HMAC-SHA256) into `account_credentials.encrypted_secrets`. There is no
  plaintext secret column, and no route ever returns secret material — only
  `GET .../credentials/health` (token status, expiry, last refresh, redacted
  error).
- Master key: `ALGOBOTS_CREDENTIAL_ENCRYPTION_KEY` (urlsafe-base64, 32 bytes).
  Generate:
  ```bash
  python -c "from algobots.api.accounts.crypto import CredentialCipher; \
    print(CredentialCipher.generate_key())"
  ```
  If unset, credential writes fail loudly (never degrade to plaintext).
- Each blob records `key_id` (sha256 prefix of the key) so rotation is
  detectable: blobs sealed under an old key fail `try_decrypt` and the sweep
  marks them `expired` with `decryption failed` rather than crashing.

## Token-health sweep (silent-refresh-or-expire)

`sweep_token_health(db, user_id=...)` (also exposed as
`POST /api/accounts/token-sweep` for the caller's accounts):

1. For each account with `token_status = active`:
   - token missing expiry or expiring after `now + ALGOBOTS_TOKEN_REFRESH_MARGIN_SECONDS`
     (default 300) → healthy, `last_checked_at` stamped.
   - otherwise → attempt silent refresh via the broker's registered refresher:
     `register_token_refresher("alpaca", refresher)`. On success the new token
     is re-sealed encrypted, expiry extended, `last_refreshed_at` stamped.
   - no refresher registered / refresher raised / undecryptable blob →
     `token_status = expired` + redacted `last_refresh_error`; the account row
     itself is untouched.
2. Per-account failures never abort the sweep (each account is isolated in
   try/except); the run returns counts `{checked, healthy, refreshed, expired,
   failed}` and the expired account ids.

## Secrets discipline (assert-tested)

- Log calls carry account ids, brokers, and outcomes only; error text passes
  through `redact()` with every decrypted secret value before persisting.
- The audit middleware records method/path/status/request-id — never bodies.
- `tests/api/test_accounts.py` asserts plaintext secrets appear in no API
  response, no log record (incl. tracebacks), no audit row, and not anywhere
  in the raw DB file bytes.

## Dashboard views

`algobots.dashboard.accounts.registry_snapshot(db, user_id)` builds the
broker-grouped, secret-free model behind the multi-account dashboard;
`render_accounts_html(snapshot)` renders it as an escaped HTML fragment.

## Migration

`alembic upgrade head` applies `0002_account_credentials` (credentials table +
`uq_accounts_user_label`). Local quickstart:

```bash
alembic upgrade head
uvicorn algobots.api.main:app
```

# A04 — Accounts, secrets, and capability registry (ALG-3100)

A tenant registers multiple accounts at the same or different brokers without
sharing credentials. A04 extends the S4.1 module (it does not fork it) with
onboarding, the encrypted secret store, the capability registry and duplicate
external-account detection.

## Registry shape (A04 additions)

- `BrokerConnection` (migration `0010`) — per-account provider/environment
  configuration, **broker session** state
  (`UNCONFIGURED→CONNECTING→CONNECTED/DEGRADED/EXPIRED/REVOKED`), egress
  allowlist, capability revision and reconciliation posture. Broker session
  authentication is separate from control-plane user authentication (A03
  auth-contract: tenant derives from the server-side session, never input).
- `ExternalAccountIdentity` — the venue-side identity as
  `sha256(provider:environment:external_account_id)`, **globally unique**: the
  same external account cannot be connected twice across tenants. The
  conflict response is generic — it never names the owning tenant, account or
  user. Ownership transfer is a later reviewed workflow (`ownership_epoch`).
- `SecretGrant` (`secret_grants`) — the `SecretResolver@1.0` ACL: one row per
  (account, assigned execution identity) with allowed environments, egress
  allowlist, rotation policy, state (`ACTIVE|ROTATED|REVOKED|EXPIRED`) and
  secret version. All three tables are tenant-scoped with composite FKs and
  PostgreSQL FORCE RLS (same policy family as A03's migration `0008`).

## Onboarding

`POST /api/broker-accounts` creates account + sealed credentials +
connection + external identity in one call. Providers come from
`api/accounts/providers.py`: the `mock` venue (development +
synthetic-paper, sessions connect immediately) and `alpaca` as a
**candidate** (paper configuration only; sessions stay `UNCONFIGURED` until
a later activation packet — no real connectivity in A04). `live` is never
onboardable in A04.

## Secret store and resolution (`src/algobots/secrets/`)

`SecretStore.resolve` is the only boundary an execution identity crosses to
open a credential, in-process (workers share the API process in the paper
core). Checks in order: reference shape → tenant scope → assigned principal →
grant state → environment → egress destination → token health. Denials are
audited (`secret.resolution_denied`) with ids and reasons only; there is no
HTTP route that returns secret material. Rotation re-seals the blob on the
same rows and bumps `secret_version` (`ROTATED`); it never mints a second
account, identity or grant. Revocation (`REVOKED`) freezes the account
(`status=frozen`) and marks the connection `needs_reconciliation` — existing
exposure surfaces as reconciliation work, never as a flat view. The key
service (`SecretKeyService`) seals with an active key and can open retired
key ids, so master-key rotation never orphans blobs.

## Capability registry

`BrokerAdapterCapabilities@1.0` (new schema version via the registry; lock
transition checked by `make verify-A04`) is the per-(provider, environment)
statement the deployment preview consults: supported order types, native
stops/protection options, client-order-ID behavior, sandbox fidelity, rate
limits and reconciliation methods. **Unknown features are disabled** — an
absent (product, order_type) row is `unsupported`:
`POST /api/broker-accounts/preview` rejects before submission.

## Secrets discipline (unchanged, still assert-tested)

No plaintext credential in any API response, log line, exception text, audit
row or job payload; blobs are Fernet-sealed before touching the database;
error text passes `redact()` with every known secret value.
