# Control-plane API — S0.2 skeleton ([ALG-3078](/ALG/issues/ALG-3078))

FastAPI + SQLAlchemy 2 + Alembic service implementing the platform's tenancy
moat: every domain row is user-scoped, every mutation is audited.

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
| `ALGOBOTS_INVITE_EXPIRE_DAYS` | 7 | Invite code TTL |

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

## Auth flow

1. **Bootstrap**: while `users` is empty, the bootstrap invite code registers
   the first user with role `owner`.
2. **Invite**: any authenticated user creates single-use invite codes
   (`POST /api/auth/invites`, default 7-day expiry).
3. **Register**: `POST /api/auth/register` with a valid code (email must be
   unique; scrypt-hashed password). Invite is claimed atomically with the row
   insert.
4. **Login**: `POST /api/auth/login` → `{access_token}` (JWT: `sub`, `iss`,
   `iat`, `exp`).
5. **Requests**: `Authorization: Bearer <token>`; inactive or missing users
   get 401.

## Tenancy rules

- Every list/read/write filters on `user_id == current_user.id`.
- Cross-tenant rows are indistinguishable from missing rows (404) — no
  existence leaks.
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
own trail at `GET /api/audit`.

## Observability

- `AccessLogMiddleware` (inner) stamps `X-Request-Id` and emits one JSON line
  per request on logger `algobots.api.access`:
  `{"event":"http","request_id","method","path","status","duration_ms","user_id"}`.
- `GET /healthz` liveness probe (docker-compose healthcheck).
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

## Endpoint map

| Route | Verbs |
| --- | --- |
| `/api/auth/register`, `/api/auth/login` | POST |
| `/api/auth/invites` | POST, GET |
| `/api/users/me` | GET |
| `/api/accounts`, `/api/accounts/{id}` | POST/GET, GET/PATCH/DELETE |
| `/api/strategies`, `/api/strategies/{id}` | POST/GET, GET/PATCH/DELETE |
| `/api/deployments`, `/api/deployments/{id}` | POST/GET, GET/PATCH/DELETE |
| `/api/orders`, `/api/orders/{id}` | POST/GET, GET/PATCH/DELETE |
| `/api/decisions` | POST/GET |
| `/api/clamp-events` | POST/GET |
| `/api/audit` | GET |
| `/healthz` | GET |

## Known follow-ups (later sprint cards)

- Rate limiting on auth endpoints; token refresh/revocation.
- Encrypted broker credentials on `accounts` (store a vault ref only).
- Postgres-backed CI integration suite (tests currently SQLite; URL is env-driven).
- Pagination on list endpoints.
