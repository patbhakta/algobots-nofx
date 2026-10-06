# Strategy DSL + Frozen Deployments (S4.2 — ALG-3091)

Condition JSON DSL, deployments as `(strategy x symbol x account)` with
freeze-at-deploy semantics, per-deployment risk envelopes, and fleet-level
breakers.

## Condition DSL (`src/algobots/strategies/dsl.py`)

A strategy row with `kind = "condition_dsl"` carries a strictly-validated
spec in `params_json`:

```json
{
  "version": 1,
  "cadence": "5m",
  "entry": {"all": [
    {"left": {"indicator": "sma", "params": {"period": 20}},
     "op": "crosses_above",
     "right": {"indicator": "sma", "params": {"period": 50}}},
    {"any": [
      {"left": {"indicator": "rsi", "params": {"period": 14}},
       "op": "lt", "right": {"value": 30}}
    ]}
  ]},
  "exit": {"left": {"indicator": "sma", "params": {"period": 20}},
           "op": "crosses_below",
           "right": {"indicator": "sma", "params": {"period": 50}}}
}
```

- **Indicators**: `sma`, `ema`, `rsi` — each with a typed `period` (`int >= 2`).
  Raw sources (`open|high|low|close|volume`) are valid series without params.
- **Operators**: `gt`, `gte`, `lt`, `lte`, `eq`, `crosses_above`,
  `crosses_below`. Crosses need the previous bar, costing +1 warmup.
- **Groups**: `{"all": [...]}` (AND) / `{"any": [...]}` (OR), arbitrarily
  nested; a group sets exactly one key and is non-empty.
- **Cadence**: `1m | 5m | 15m | 1h | 1d` (evaluation interval, typed enum).
- **Warmup**: computed from the spec — `sma/ema(n)` need `n` bars, `rsi(n)`
  needs `n+1`, crosses add one. An explicit `warmup_bars` must cover the
  computed minimum.
- **Strictness**: `extra="forbid"` everywhere. Unknown indicator, unknown
  param key, unknown operator, unknown cadence, or unknown field rejects
  (HTTP 422 at deploy time).

`artifact_hash(spec)` is the sha256 of the canonical JSON dump (sorted keys,
no whitespace) of the validated spec — the frozen artifact identity.

## Evaluation (`src/algobots/strategies/eval.py`)

`evaluate(spec, bars)` is pure — no I/O, no clocks, no DB. Indicator math:

- SMA(n): mean of the trailing n values.
- EMA(n): seeded with SMA(first n), then `k = 2/(n+1)` recursion.
- RSI(n): Wilder smoothing; `avg_loss == 0` → 100.

Warmup violations raise `InsufficientWarmup` (never silently half-evaluate).
Decisions are explainable: every leaf is plain arithmetic over the bar window.

## Deployments (`src/algobots/api/deployments/`)

A deployment is `(strategy x symbol x account)` — **frozen at deploy**:

- `frozen_spec_json` — strategy name/kind + normalized DSL spec captured at
  deploy; editing the strategy afterwards never reaches a running deployment.
- `artifact_hash` — sha256 of the canonical frozen spec (drift-detectable).
- Risk envelope — `max_order_value` and `max_daily_loss` are REQUIRED
  explicit decimals at deploy (money rails never default; caps frozen with
  the snapshot).
- `deployments` reference `account_id` from the S4.1 registry; credentials
  are never copied into deployment rows.

Routes (tenant-scoped; another tenant's rows 404):

| Route | Purpose |
| --- | --- |
| `POST /api/deployments` | Deploy + freeze (422 invalid DSL, 409 duplicate tuple) |
| `GET /api/deployments` / `GET /{id}` | Read (includes frozen spec, hash, effective state) |
| `PATCH /api/deployments/{id}` | User intent: `running|paused|stopped` |
| `DELETE /api/deployments/{id}` | Remove |
| `POST /api/deployments/{id}/risk/daily-loss` | Report signed P&L vs frozen cap |
| `POST /api/deployments/{id}/breaker/reset` | Close one deployment's breaker |
| `GET/POST /api/deployments/fleet/breaker` | Fleet breaker state / trip / reset |

**Duplicate guard**: at most one ACTIVE deployment per
`(strategy, symbol, account)` — same tuple (case-insensitive symbol) →
`409` with a clear message. `stopped` frees the tuple. A partial unique
index (`uq_deployments_active_tuple`, migration `0003`) backstops the
service-level check.

**Effective state**: `status` is user intent; halts are tracked separately.
`effective_state = halted` when the deployment's own breaker is open
(`halt_source: deployment_breaker`) or the fleet breaker is open
(`halt_source: fleet_breaker`); otherwise it equals `status`.

**Breakers**:

- Per-deployment: a daily-loss report (`daily_pnl`, signed) against the
  FROZEN envelope trips at loss >= cap — only that deployment halts.
  Exits are privileged everywhere (see `risk/breakers.py`, `risk/envelopes.py`).
- Fleet: `POST /api/deployments/fleet/breaker {"action":"trip"}` opens the
  caller's fleet breaker and halts EVERY deployment in their scope; `reset`
  resumes exactly the fleet-halted ones.

## Observability

Secret-free structured events on the `algobots.api.deployments.service`
logger: `deployment_created`, `deployment_breaker_tripped`,
`deployment_breaker_reset`, `fleet_breaker_tripped`, `fleet_breaker_reset`
— ids, symbols, hashes, money caps only. Deployment rows contain no
credential material by construction.

## Migrations

`0003_strategy_deployments` adds the freeze/envelope/breaker columns to
`deployments`, creates `fleet_breakers` (one row per user), and the partial
unique duplicate-guard index. Verified up/down in the API test suite.
