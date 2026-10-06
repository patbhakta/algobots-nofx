# algobots.execution

Delta-vs-holdings order planning and execution discipline. **Dry-run by
construction**: nothing in this package opens a socket, and nothing
dispatches — `plan_orders` produces a serializable plan artifact, and
`ExecutionDiscipline.tick` only decides *what would be sent next* (venue
adapters are out of scope).

Modules:

- `planner` — `plan_orders(target_weights, holdings, market_state, config) -> OrderPlan`
- `governor` — `TurnoverGovernor` (turnover cap; scales down, never rejects)
- `discipline` — `ExecutionDiscipline` / `OrderInstruction` (jev-trade mechanics port)
- `quantity` — shared quantity precision (`QTY_QUANT = 1e-8`) and Decimal coercion

## Planner deltas

| Input state                              | Behavior                                                                                     |
| ---------------------------------------- | -------------------------------------------------------------------------------------------- |
| `target > 0`                             | `desired_qty = (target × NAV) / price`, delta = desired − current                             |
| `target ≤ 0` or absent from target set   | **sell-to-zero**: liquidate the full current position                                         |
| Symbol held but price `None`/untradable  | No order; listed in the artifact's `unknown`                                                  |
| `delta == 0` (or below `1e-8` precision) | No order                                                                                      |
| Sign flip (long → negative target)       | Planned as exit-to-zero only; the reverse leg lands on a later planning pass                   |
| Sell sizing clamp                        | A sell never exceeds current long holdings; a covering buy never exceeds the current short leg |
| Order intent                             | `exit` when the order reduces the existing position (including reductions and liquidations); otherwise `entry` |

## Governor policy

- `turnover = Σ|order notional| / NAV`.
- `turnover_cap` and `nav` are **required** `Decimal` constructor args — no silent defaults on money rails.
- Projected turnover over cap → every quantity is scaled by `cap / projected_turnover` (rounded DOWN to `1e-8`), then sells are re-clamped to current holdings (and covering buys to current short legs).
- **The governor never rejects.** Worst case is `scale_factor < 1`, recorded on the artifact alongside `projected_turnover` and post-scale `turnover`.
- Orders scaled below `1e-8` quantity are dropped.

## Risk-rail integration (S1.2)

- With `PlannerConfig.risk_gate` set, every order passes `RiskGate.approve_order`.
- A clamped entry is shrunk to the approved notional, surfaces a `clamp: {limit, before, after}` annotation on the order, and the gate writes exactly one `ClampEventRow` via its existing sink.
- Exits are privileged: never blocked, never clamped, no audit row.
- A denied entry (daily-loss envelope, breakers) is dropped from `orders` and listed in `gated_out` with the gate's reason.

## Discipline rules (jev-trade port)

| Situation                     | Action                                                                        |
| ----------------------------- | ----------------------------------------------------------------------------- |
| Entry (any side)              | Post-only limit, **one tick inside the touch**: buy `ask − tick`, sell `bid + tick` (cannot cross by construction) |
| Exit / reduction              | IOC with `reduceOnly=true`, no limit price; quantity ≤ the account's position   |
| Exit with no account position | Hold                                                                          |
| State unknown (no bid/ask)    | Hold                                                                          |
| Upstream unavailable          | Hold                                                                          |
| Market closed                 | Hold — nothing dispatches                                                     |
| Any hold                      | Pulls stale queued orders                                                     |
| Sequencing                    | At most **one** instruction per `tick`; newest plan supersedes and pulls stale queued orders |

## Market-closed policy

When `market_state.is_open` is false the planner still emits the **full**
plan artifact, annotated `market_closed: true` and
`dispatch_at: <market_state.next_open>`. Nothing dispatches until the next
open: `ExecutionDiscipline.tick` returns `None` for a closed market.

## Artifact

`OrderPlan` is a pydantic model (`extra="forbid"`) serializable with
`model_dump_json()`: `inputs_hash` (sha256 over canonical sorted-JSON
inputs), `market_closed`, `dispatch_at`, `projected_turnover`, `turnover`,
`scale_factor`, `orders[{symbol, side, quantity, notional, intent,
clamp?}]`, `unknown`, `gated_out`, and `discipline` policy annotations.
Golden-file tests pin three fixture artifacts byte-for-byte under
`tests/execution/golden/`.
