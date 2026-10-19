# Owner-issued registration

Public registration is disabled even on empty databases and even when the legacy
registration toggle is true. Existing accounts and password hashes are unchanged.
An empty installation requires an operator-provisioned owner; there is no public
bootstrap bypass.

Pat signs in with the existing pat@bhakta.us account and sends an authenticated
POST /api/invites with JSON {"email":"friend@example.com"}. The response contains
register_path; prepend the application's public origin and share privately.
The link uses /register#invite=TOKEN, keeping the bearer token out of HTTP access
logs and referrers. Do not log the issuance response or store it in tickets.

Invites expire after seven days and are bound to the recipient email. No other
account can issue invites. Registration consumes the invite atomically with user
creation. SHA-256 hashes alone are stored. Creation and redemption have audit rows.
These are NoFX auth endpoints, not gateway endpoints; the gateway contract and
its generated client do not change. The G1 gateway/order execution path is unchanged.

The Go model ports A03 TenantInvite and its create/redeem service semantics from
algobots/src/algobots/api/memberships: 256-bit random tokens, SHA-256 storage,
email binding, expiry, conditional consumption, and transaction-bound auditing.
No membership is imported across the independent Python and NoFX identity stores.

Verification: go test ./store -run TestInviteLifecycle -count=1 and
go test ./api -run 'TestInviteOnlyRegistration|TestTenantSessionClaims|TestTenantIsolation' -count=1.
