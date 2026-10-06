# Control-plane API — S0.2 skeleton ([ALG-3078](/ALG/issues/ALG-3078)) + A03 tenancy ([ALG-3099](/ALG/issues/ALG-3099))

FastAPI + SQLAlchemy 2 + Alembic service implementing the platform's tenancy
moat: every tenant-owned row carries a `tenant_id` derived from an
authenticated membership, PostgreSQL enforces it with row-level security, and
every mutation is audited.

Implements the [ALG-3076](/ALG/issues/ALG-3076) MVP roadmap card S0.2.
Schema shapes informed by Fincept `broker_accounts` ([ALG-3070](/ALG/issues/ALG-3070))
and NoFX user-scoped stores ([ALG-3069](/ALG/issues/ALG-3069)).

## Stack

| Concern | Choice |
| --- | --- |
| HTTP | FastAPI (`src/algobots/api/main.py`) |
| ORM | SQLAlchemy 2 (`models.py`), sessions per request (`database.py`) |
| Migrations | Alembic (`alembic.ini`, `src/algobots/api/migrations/`) |
| Auth | JWT (PyJWT, HS256) + scrypt password hashing (stdlib) |
| Config | pydantic-settings, env prefix `ALGOBOTS_` (`config.py`) |

## Configuration

| Env var | Default | Purpose |
| --- | --- | --- |
| `ALGOBOTS_DATABASE_URL` (or `DATABASE_URL`) | `sqlite:///./algobots.db` | SQLAlchemy URL; `postgresql://` auto-upgrades to `postgresql+psycopg://` |
| `ALGOBOTS_JWT_SECRET` | dev value | HS256 signing key — set ≥32 bytes in any real deployment |
| `ALGOBOTS_JWT_ISSUER` / `_ALGORITHM` | `algobots` / `HS256` | Token claims |
| `ALGOBOTS_ACCESS_TOKEN_EXPIRE_MINUTES` | 60 | Token TTL |
| `ALGOBOTS_BOOTSTRAP_INVITE_CODE` | `ALGOBOTS-BOOTSTRAP` | Valid only while the `users` table is empty; first registrant becomes `owner` |
| `ALGOBOTS_INVITE_EXPIRE_DAYS` | 7 | Platform invite code and tenant invite TTL |
| `ALGOBOTS_OIDC_ISSUER` / `_AUDIENCE` / `_SHARED_SECRET` | empty / `algobots` / empty | Local/fake OIDC provider (HS256); empty issuer disables `POST /api/auth/oidc/login` |

## Schema (migration `0001_control_plane`)

| Table | Tenancy | Notes |
| --- | --- | --- |
| `users` | — | email unique (lowercased), scrypt hash, role `owner`/`member` |
| `invite_codes` | creator-scoped | single-use, expiring; claimed_by tracked |
| `accounts` | `user_id` | broker account, `mode` paper/live, status |
| `strategies` | `user_id` | kind + `params_json` |
| `deployments` | `user_id` | strategy × account, status lifecycle |
| `orders` | `user_id` | side/type/qty/limit_price, status lifecycle |
| `decisions` | `user_id` | strategy decision record for evals (confidence, rationale) |
| `clamp_events` | `user_id` | risk clamp application trail |
| `audit_log` | `user_id` nullable | one row per mutating request, incl. failures |

Migration `0005_tenant_memberships` (A03) adds `tenants`,
`tenant_memberships`, `tenant_invites`, `auth_sessions` and `account_grants`,
stamps `tenant_id` (NOT NULL) on `accounts`, `strategies`, `orders`,
`decisions` and `clamp_events` (backfilled from each writer's personal tenant),
and a nullable `tenant_id` on `audit_log`. `deployments`, `account_credentials`
and the S4.3 approval tables have no `tenant_id` column yet. Their routers
check `user_id`, and A03 additionally requires an active membership and the
role matrix for them (`get_current_user`) and filters them to the active
tenant's accounts with ORM criteria (`algobots.api.auth.context`).

## Auth flow

Registration is invite-only; there is no public path.

1. **Bootstrap**: while `users` is empty, the bootstrap invite code registers
   the first user with platform role `owner`.
2. **Platform invite**: platform owners mint single-use codes
   (`POST /api/auth/invites`). A user registered with one gets a personal
   tenant they own.
3. **Tenant invite**: a tenant owner invites an email with role `member` or
   `viewer` (`POST /api/memberships/invites`). The 256-bit token is returned
   once and stored only as SHA-256. It is single-use, expires, and is bound to
   that recipient. A new user registers with `tenant_invite_token`; an
   existing user redeems it at `POST /api/memberships/invites/redeem`.
   Redemption is a guarded `UPDATE`, so concurrent redeemers produce exactly
   one membership.
4. **Login**: `POST /api/auth/login` (or `POST /api/auth/oidc/login` with an ID
   token from the configured local provider; OIDC never provisions users)
   creates an `auth_sessions` row and returns a JWT with `sub`, `sid`, `iss`,
   `iat` and `exp`. The active tenant is session state: the personal tenant,
   else the oldest active membership.
5. **Requests**: every request re-checks the session row (not revoked, not
   expired) and the active membership. **Declared revocation window: 0 s**
   (target ≤ 60 s). `POST /api/auth/logout` revokes the session. Revoking a
   member revokes their sessions in that tenant and their grants.
6. **Switch**: `POST /api/tenants/{id}/switch` changes the session's tenant
   after a membership check. The tenant is never read from a body or header.

## Roles and grants

| Action | owner | member | viewer |
| --- | --- | --- | --- |
| `tenant.read`: read/list/export tenant rows | ✓ | ✓ | ✓ |
| `resource.write`: create/update/delete, post orders | ✓ | ✓ | — |
| `membership.manage`: invite, change role, revoke, grants | ✓ | — | — |
| `audit.read_all`: all tenant audit rows, not only one's own | ✓ | — | — |

Routers outside A03 that depend on `get_current_user` get the same matrix by
HTTP method: reads need `tenant.read`, every other method needs
`resource.write`. Unknown roles are denied. A tenant always keeps one active
owner: owner rows are locked (`FOR UPDATE`) before a demotion or revocation and
re-checked afterwards, so concurrent demotions can't remove the last one.
Ownership is never conferred by invite. Denials return 403 and write a
`DENY` audit row with the action and role, never the body. **Trading authority
is separate from membership**: `account_grants` rows (per account, per member,
from `ALLOWED_GRANTS[USER]`, viewers only `ACCOUNT_READ`) are the only source
of a member's `Principal@1.0` grants. A new member holds none.

## Tenancy rules

- Every tenant-owned list/read/write filters on the session's active tenant.
- Cross-tenant rows are indistinguishable from missing rows (404) — no
  existence leaks.
- Children reference parents through composite `(tenant_id, id)` foreign keys
  (`orders`/`clamp_events` → `accounts`, `decisions` → `strategies`,
  `account_grants` → `accounts`).
- Lists accept `limit` and an opaque `cursor`; the next cursor is returned in
  `X-Next-Cursor`. Cursors are HMAC-signed and bound to the tenant, so one used
  under another tenant gets a 400.
- **PostgreSQL row-level security**: `ENABLE` + `FORCE` on the five
  tenant-owned tables and `account_grants`, with policy
  `tenant_id = current_setting('app.tenant_id')`. The API binds the tenant with
  `set_config('app.tenant_id', id, true)` (transaction-local) at the start of
  every transaction (`algobots.api.auth.context`). An unset setting matches no
  rows. Connections returned to the pool run `RESET app.tenant_id`, and are
  invalidated if the reset fails. The API **must connect as a non-superuser,
  NOBYPASSRLS role** that is a member of `algobots_app`, which migration 0005
  creates when it can. Superusers and BYPASSRLS roles skip the policies, so
  background jobs that need cross-tenant reads need their own role.
- Referential guards: deleting an account with deployments/orders/clamp
  events, or a strategy with deployments/decisions, returns 409.
- Filled orders are immutable history: delete only allowed for
  `pending`/`cancelled`/`rejected`.

## Audit middleware

`AuditMiddleware` (outermost) writes one `audit_log` row per mutating request
(POST/PUT/PATCH/DELETE) regardless of outcome: actor (JWT `sub`, nullable for
anonymous failures), method, path, status code, `resource`/`resource_id`
(from router-set `X-Audit-Resource*` response headers), and the request id.
Audit failures are logged, never surfaced as API errors. Tenants read their
own trail at `GET /api/audit` (owners see every row in their tenant). A03
adds typed `EVENT` rows (`tenant.created`, `invite.created`/`revoked`,
`membership.created`/`role_changed`/`revoked`, `grant.added`/`removed`,
`session.tenant_switched`) written in the same transaction as the change, and
`DENY` rows for policy refusals.

## Observability

- `AccessLogMiddleware` (inner) stamps `X-Request-Id` and emits one JSON line
  per request on logger `algobots.api.access`:
  `{"event":"http","request_id","method","path","status","duration_ms","user_id"}`.
- `GET /healthz` liveness probe (docker-compose healthcheck); `GET /readyz`
  readiness (503 until the database answers).
- The `audit_log` table doubles as a durable mutation ledger.

## Running & tests

```bash
pip install -e ".[dev]"
alembic upgrade head
uvicorn algobots.api.main:app
pytest                       # full suite incl. integration tests
ruff check . && ruff format --check .
```

Tests provision a throwaway SQLite DB **via the real Alembic migration**
(session fixture), then exercise register → invite → login → CRUD over HTTP,
tenant isolation, audit-per-mutation (direct DB asserts), structured access
log, and an Alembic upgrade → downgrade → upgrade cycle. CI
(`ruff` + `pytest`) runs on every push/PR.

A03 acceptance (`make verify-A03`): `tests/packets/A03/`. The RLS and pooled
connection cases (`test_pg_rls.py`) need a real PostgreSQL. Set
`ALGOBOTS_A03_PG_ADMIN_URL` to a role that can create databases and roles. The
test creates a throwaway database and a NOSUPERUSER NOBYPASSRLS login role.
Without the variable those cases skip as BLOCKED.

## Endpoint map

| Route | Verbs |
| --- | --- |
| `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/oidc/login` | POST |
| `/api/auth/invites` | POST, GET |
| `/api/users/me`, `/api/me`, `/api/tenants` | GET |
| `/api/tenants/{id}/switch` | POST |
| `/api/memberships` | GET |
| `/api/memberships/{id}` | PATCH, DELETE |
| `/api/memberships/invites`, `/api/memberships/invites/{id}`, `/api/memberships/invites/redeem` | POST/GET, DELETE, POST |
| `/api/memberships/{id}/grants`, `/api/memberships/grants/{id}` | GET/POST, DELETE |
| `/api/export` | GET |
| `/api/accounts`, `/api/accounts/{id}` | POST/GET, GET/PATCH/DELETE |
| `/api/strategies`, `/api/strategies/{id}` | POST/GET, GET/PATCH/DELETE |
| `/api/deployments`, `/api/deployments/{id}` | POST/GET, GET/PATCH/DELETE |
| `/api/orders`, `/api/orders/{id}` | POST/GET, GET/PATCH/DELETE |
| `/api/decisions` | POST/GET |
| `/api/clamp-events` | POST/GET |
| `/api/audit` | GET |
| `/healthz`, `/readyz` | GET |

## Known follow-ups (later sprint cards)

- Rate limiting on auth endpoints; token refresh.
- Encrypted broker credentials on `accounts` (store a vault ref only).
- A PostgreSQL service in CI so `test_pg_rls.py` runs on every push. Today it
  runs locally against real PostgreSQL 16 and skips in CI.
- `tenant_id` + RLS on `deployments`, `account_credentials` and the approval
  tables (owned by their packets); service roles for background sweeps.
- Tenant-scope `fleet_breakers` (A11, [ALG-3186](/ALG/issues/ALG-3186)): the breaker is per
  user, so a reset un-halts that user's deployments in every tenant.
