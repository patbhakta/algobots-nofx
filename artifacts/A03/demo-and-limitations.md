# A03 — Demo and limitations ([ALG-3099](/ALG/issues/ALG-3099))

## Demo

`make demo-A03` (output: `artifacts/A03/demo-output.txt`) stands in for "two
browser sessions". Alice and Bob each own a workspace. Each seeds an account
labelled `main`, a `momentum` strategy and an AAPL order, so the two workspaces
look the same. Then:

- each session lists only its own `main` account, and its switcher fragment
  shows only its own workspace;
- each side's GET, PATCH and DELETE on the other's account id returns 404, and
  the other's ids never appear in `GET /api/export`;
- a viewer invited into Alice's workspace can read but gets 403 on posting an
  order;
- after Alice revokes the viewer, the viewer's old token gets 401 on its next
  request.

The demo runs on a throwaway migrated SQLite file with synthetic users. The
same isolation against PostgreSQL row-level security is shown by
`tests/packets/A03/test_pg_rls.py::test_ac2_http_requests_interleaved_on_pooled_connections`.

## What A03 delivers

- Migration `0005` (after `0004`): tenants, memberships, hashed single-use
  invites, server-side sessions and account grants. It backfills a personal
  tenant per existing user, adds `tenant_id` and composite foreign keys, and
  turns on `FORCE ROW LEVEL SECURITY` on PostgreSQL.
- Session-bound JWTs (`sid`), with the session and membership re-checked on
  every request. Declared revocation window: **0 s**.
- Role matrix (owner, member, viewer). Member management is owner-only.
  Denials are audited without secrets, and membership, role, invite, grant and
  switch changes are audited as typed events.
- Invite-only registration. Public registration has no path, and platform
  invites are limited to platform owners.
- A grant seam that is separate from membership. `principal_for` builds a
  `Principal@1.0` from explicit grants only.
- Tenant-bound keyset cursors, `GET /api/export`, `/api/me`, `/api/tenants`,
  `/api/memberships`, `/readyz`, a local OIDC login seam, and a dashboard
  switcher fragment.

## Limitations and follow-ups

1. **PostgreSQL evidence is local, not CI.** AC1's database layer, AC2 and the
   PostgreSQL redemption race ran against a real PostgreSQL 16 (a throwaway
   socket-only cluster). GitHub CI has no PostgreSQL service, so
   `test_pg_rls.py` skips there with a BLOCKED reason. Adding a `postgres:16`
   service plus `ALGOBOTS_A03_PG_ADMIN_URL` is outside the A03 write scope and
   is proposed to the workflow owner.
2. **RLS applies only to a non-bypass role.** Superusers and `BYPASSRLS` roles
   skip the policies. `deploy/docker-compose.yml` connects as `algobots`,
   which the official postgres image creates as a superuser (`POSTGRES_USER`),
   so production must switch the API to a login role in `algobots_app` before
   RLS protects anything. Until then, isolation rests on
   the application filters, which every AC1 test also covers.
3. **Background jobs** that read across tenants (the S4.1 token-health sweep)
   see no rows as the app role. They need their own service role, which is an
   ops or A04 decision.
4. **Tables outside A03 scope have no `tenant_id` column yet.** `deployments`,
   `account_credentials`, `approval_requests`, `broadcasts` and `action_ledger`
   still check `user_id` in their own routers. Since review round 1
   ([ALG-3183](/ALG/issues/ALG-3183) finding 1), A03 narrows them anyway:
   `get_current_user` requires an active membership and applies the role
   matrix by method, and ORM criteria filter those tables to the active
   tenant's accounts. A revoked member, a viewer, and a user acting from a
   second tenant are refused (`tests/packets/A03/test_routers_outside_a03.py`).
   What remains: there is no PostgreSQL RLS on those tables, and two members of
   the same workspace still can't act on each other's deployments or
   approvals. `fleet_breakers` stays a per-user kill switch: it can only halt
   that user's own deployments, never start them. The owning packets should add
   `tenant_id` + RLS on top of 0005.
5. **OIDC is a development seam**: an HS256 shared secret for a local or fake
   provider, with no JWKS, nonce or PKCE. It authenticates existing users only
   and never provisions anyone. A real IdP needs separate authorization.
6. **No rate limiting** on auth or invite endpoints yet.
7. **Make targets are proposed, not integrated.** `verify-A03` and `demo-A03`
   are in their own commit (`8fc3997`) for the make-targets owner (A01).
8. **Recovery**: downgrading 0005 keeps every 0001–0004 row and every audit
   row, but loses workspace structure. Export `tenants`,
   `tenant_memberships`, `tenant_invites` and `account_grants` first. If the
   database is unavailable, authentication fails closed (401), and a missing
   tenant context matches no rows.
