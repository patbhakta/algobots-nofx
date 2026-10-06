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
