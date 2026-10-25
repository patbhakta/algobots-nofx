# Multi-Tenant Login (AlgoBots Investor Dashboard)

Each login on the AlgoBots fork is an **investor tenant**: one user account
owns — and is scoped to — its own traders, strategies, exchange accounts,
AI model configs and wallet keys. No tenant can read another tenant's data
through the API. This document is the operator guide for the tenant model,
the registration gate, and tenant provisioning.

## Tenant model

- **Tenant = login account (1:1).** The `users` row is the tenant; its `id`
  is the tenant scope. Every data table (`traders`, `strategies`,
  `exchanges`, `ai_models`, orders, positions, decisions) already carries
  `user_id`, and every API handler resolves rows through
  `user_id = caller`. That column **is** the tenant boundary.
- **Sessions carry tenant identity.** The JWT issued at login/register has
  `user_id`, `email` and an explicit `tenant_id` claim (equal to `user_id`,
  named to match the main AlgoBots repo's `tenant_id` contract). The auth
  middleware sets both `user_id` and `tenant_id` in the request context.
  Tokens issued before this field existed keep working: the middleware
  falls back to `user_id` when `tenant_id` is absent.
- **Isolation guarantees are test-enforced** in
  `api/handler_tenant_test.go` (`TestCrossTenantIsolation`): tenant B
  cannot list or fetch tenant A's strategies, traders, trader config,
  exchanges or orders — cross-tenant reads return 404, and list endpoints
  never include another tenant's rows.

## Registration gate (backend-controlled)

Public self-registration at `POST /api/register` (page `/register`) is
gated server-side:

1. **Bootstrap**: while the system has no users, registration is open so
   the first tenant can be created (unchanged first-time-setup behavior).
2. **After initialization** the gate is **closed by default** — the
   `/register` page shows the *Registration Closed* screen. This preserves
   the historical single-tenant deployment behavior.
3. **Operator toggle**: the `registration_enabled` key in the
   `system_config` table reopens (or closes) public registration. It is
   exposed to the frontend via `GET /api/config`
   (`registration_enabled`), and it is **only** writable from the host
   shell (never by an API route):

```bash
nofx set-registration --enable   # open /register for new investor tenants
nofx set-registration --disable  # close it again (default state)
```

## Provisioning a tenant

Two supported paths:

**Self-service (when the gate is open)** — the investor registers at
`/register`; the account is created, default strategies are seeded, and
the session starts immediately.

**Operator CLI (always available, ignores the gate)** — requires shell
access to the host, which is operator authority (same security posture as
`nofx reset-password`):

```bash
nofx create-user --email investor@example.com
#  ✓ Investor tenant created.
#    email: investor@example.com
#    tenant_id: 3f9c...
#    password: <random, printed once>
```

Pass `--password 'S3cret!23'` to set a specific password (min 8 chars);
omit it and a random one is generated and printed once. Default strategies
are created lazily the first time the tenant opens the strategy list.
Passwords can be rotated with `nofx reset-password --email …`.

## What this does not change

- The NoFX↔Nautilus bridge surfaces (control plane + bridge channel) are
  untouched by the tenant model; bridge traffic does not flow through the
  tenant-scoped dashboard API.
- Wallet keys and exchange credentials remain encrypted at rest and are
  only ever resolved through the owning tenant's context.
