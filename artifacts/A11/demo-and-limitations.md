# A11 — Strategy studio & account fan-out: demo and limitations

Evidence packet for A11 (ALG-3107 packet, slices A11-1..A11-4: ALG-3256
studio, ALG-3281 paper runner, ALG-3282 campaigns/ownership, ALG-3283 this
packet). Everything below was executed against the real app on this checkout;
screenshots are committed next to this file. Acceptance verdicts live in
[`acceptance.json`](acceptance.json), raw junit in
[`test-results/`](test-results/).

## Booting the app

```bash
alembic upgrade head
ALGOBOTS_DEMO_WORKERS_ENABLED=1 uvicorn algobots.api.main:app --port 8000
```

`ALGOBOTS_DEMO_WORKERS_ENABLED=1` starts one template paper worker per
deployment (the supervisor flips a deployment `pending -> running` only after
its worker's first heartbeat — never on deploy). The committed evidence runs
used a scratch state dir and a harness-picked port; the URLs below use
`http://127.0.0.1:8000/` for readability.

## Demo script — two strategies across four paper accounts

The four demo accounts: `eq-a` ($1,000), `eq-b` ($2,500), `eq-c` ($500) —
equities paper — and `laya` (Kalshi paper; **ineligible** for equities
templates, so every equities fan-out over all four accounts must skip it
explicitly).

### 1. Configure strategy 1 — Trend crossover

- Open **`http://127.0.0.1:8000/demo/studio`** (scope: all four accounts).
- Pick *Trend crossover* (`trend`), edit params to 5m cadence, fast 5 / slow
  13, symbol SPY → saving appends **version 2** (`c76ff035b50d`); version 1
  stays deployed-able and nothing running changes (AC2).
- Preview the fan-out across the four accounts:
  `http://127.0.0.1:8000/demo/api/studio/preview?version=c76ff035b50d…&accounts=eq-a&accounts=eq-b&accounts=eq-c&accounts=laya&mode=equal&amount=800`
  → three allocation lines + one skip line: `laya — equities strategy cannot
  trade on a kalshi account` (AC3, preview half).
- Deploy from the page (`POST /demo/studio/deploy`) → campaign
  `cmp-c76ff035-1`, children `eq-a 400 · eq-b 400`, outcome
  **`SUCCEEDED · 2/2`** (both filled).

### 2. Configure strategy 2 — Range / RSI

- Back on `/demo/studio`, pick *Range / RSI* (`range_rsi`), 5m, period 6,
  bands 35/65, symbol QQQ → version 2 (`c9720de8…`).
- Preview with `mode=pct&pct=100` over all four accounts: eq-a $600 (headroom
  capped), eq-b $2,100, eq-c $500, laya skip.
- Deploy → campaign **`cmp-c9720de8-2`**. The per-account outcome, six hours
  later:

  | account | child status | reason |
  |---|---|---|
  | eq-a | filled | 5 orders filled |
  | eq-b | rejected-by-risk | 2100.00 USD over max order value; gate allows 1000 USD per deployment |
  | eq-c | filled | 5 orders filled |
  | laya | skipped | equities strategy cannot trade on a kalshi account |

  The campaign header reads **`PARTIAL · 2/4`** — never `SUCCEEDED` — and
  eq-b's rejection reversed nothing on eq-a/eq-c (AC5). Because trend owns SPY
  on eq-a/eq-b, a later conflicting SPY version is skipped at preview naming
  the owning deployment; the QQQ campaign deploys alongside it (AC4).

### 3. Inspect per-account results

- Campaign view (Campaigns panel + per-child status + order timeline):
  **`http://127.0.0.1:8000/demo/studio?campaign=cmp-c9720de8-2`**
  — screenshots:
  [`ALG-3282/studio-campaign-partial-desktop.png`](ALG-3282/studio-campaign-partial-desktop.png)
  (1440px),
  [`ALG-3282/studio-campaign-partial-mobile.png`](ALG-3282/studio-campaign-partial-mobile.png)
  (390px).
- Per-account orders (only that account's orders, each row labelled with its
  deployment id + artifact hash): `http://127.0.0.1:8000/demo/api/orders?account=eq-a`
  — screenshots:
  [`ALG-3281/demo-eq-a-desktop.png`](ALG-3281/demo-eq-a-desktop.png),
  [`ALG-3281/demo-eq-a-mobile.png`](ALG-3281/demo-eq-a-mobile.png);
  aggregate view:
  [`ALG-3281/demo-all-desktop.png`](ALG-3281/demo-all-desktop.png),
  [`ALG-3281/demo-all-mobile.png`](ALG-3281/demo-all-mobile.png).
- Campaign JSON (parents, children, live statuses, timelines with risk-denial
  reasons): `http://127.0.0.1:8000/demo/api/campaigns`.
- Recovery, exercised live: pausing `cmp-c9720de8-2` → `PAUSED · 2/4` (new
  entries held, exits still fill); disabling Range / RSI v2 kept all
  deployments and history; re-enable restored preview.

Live-check narratives: [`ALG-3281/README.md`](ALG-3281/README.md),
[`ALG-3282/README.md`](ALG-3282/README.md).

## Exclusions (scope decisions, not gaps)

- **No Python editor.** Strategies are three typed templates — Trend
  crossover, Range / RSI, Periodic ETF allocation — plus the three live demo
  strategies (Laya, Jev, coin-flip control) whose parameters are fixed in
  code. Users compose parameter sets only; arbitrary code is deliberately
  absent from the studio.
- **No derivative baskets.** The ETF allocation template trades the
  underlying equities only. There is no options/futures basket construction
  anywhere in A11.
- **No cross-account atomicity.** A fan-out is one parent with independent
  children. A child rejected by risk or skipped leaves its siblings' fills in
  place by design; there is no all-or-nothing deploy and no rollback of
  filled siblings.

## Remaining limitations, stated honestly

1. **Prices are synthetic bars.** The runner consumes deterministic synthetic
   OHLCV (`src/algobots/demo/bars.py`), not market data; the page says so.
   Nothing in A11 is validated against real quotes.
2. **Fleet breakers are user-scoped, not tenant-scoped (AC6 BLOCKED).** On
   this commit a fleet-breaker reset resumes the user's deployments across
   all their scopes; the (tenant, user) scoping from ALG-3186 rides the A03
   branch `feat/alg-3099-a03-tenant-auth` (`db6f400`) and lands with the A03
   integration. Until then AC6 is BLOCKED, not PASS.
3. **Studio state is one JSON file.** `studio.json` next to the kill switch,
   written atomically under a process-local lock — fine for the single-node
   demo; it is not a multi-writer database (the control-plane API lanes use
   Alembic-migrated stores; the demo studio does not).
4. **Money is capped by demo constants.** $100 minimum allocation per
   deployment, $1,000 max order value per deployment (the risk gate that
   rejected eq-b above); the demo studio's daily-loss cap is effectively
   unlimited ($1,000,000 envelope). These are demo constants, not configurable
   per user.
5. **Fixed demo account set.** `eq-a`/`eq-b`/`eq-c`/`laya` with hard-coded
   paper balances; the studio has no account provisioning flow.
6. **Attribution is per-deployment, not per-fill-P&L.** Orders carry
   deployment id + artifact hash and per-account statistics aggregate them,
   but there is no per-strategy realized-P&L attribution accounting yet.
7. **Template cadences trade on wall-clock steps.** The runner evaluates on
   bar cadence with a synthetic clock in tests and the supervisor's schedule
   live; there is no backfill/catch-up for downtime beyond restart
   reconciliation (which does not duplicate orders).
8. **The studio is a `/demo` surface.** It sits behind the demo scope model
   (campaigns follow the studio scope), not the tenant-RLS control plane;
   tenant-scoped studio usage arrives with the A03 integration.
