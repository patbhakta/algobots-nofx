# algobots.risk — the hard rail between conviction and money

**Conviction requests, risk disposes.** Everything in this package is
deterministic arithmetic that sits between the models and the money. No
clamp is negotiable, and every firing writes exactly one `ClampEventRow`
to an audit sink.

## Layout

| Module | What it does |
|---|---|
| `limits.py` | Vendored VERBATIM from [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (MIT, pinned at commit `154a8b2f46dc`). Per-ticker (`max_position_pct`) and gross (`max_gross_exposure`) weight clamps. |
| `envelopes.py` | Per-deployment money caps (`RiskEnvelope`): `max_order_value`, `max_daily_loss`. Both are **required** `Decimal` fields — an envelope missing an explicit cap fails validation. No silent defaults on money rails. |
| `breakers.py` | Rate breakers (`RateBreakers`) with Fincept manual Algo §19 defaults. **Exits are privileged: nothing in this module ever blocks an exit or reducing order.** |
| `audit.py` | `ClampEventRow`, the `ClampEventSink` protocol, `InMemorySink`, `JsonlSink`, and `RiskGate` — the wiring point so every firing writes exactly one audit row. |

## Rate-breaker defaults (Fincept manual Algo §19, via ALG-3070 study §R4)

| Scope | Breaker | Default | Trips when | Recovers when |
|---|---|---|---|---|
| Per-deployment | Orders / minute | **10** | 10 orders recorded in any 60 s sliding window — the 11th order is denied | the oldest order ages out of the 60 s window |
| Per-deployment | Orders / day | **200** | 200 orders recorded in any 24 h sliding window | the oldest order ages out of the 24 h window |
| Fleet-wide | Entries / minute | **75** | 75 entries recorded in any 60 s sliding window | the oldest entry ages out of the 60 s window |
| Fleet-wide | Entries / day | **500** | 500 entries recorded in any 24 h sliding window | the oldest entry ages out of the 24 h window |
| Per-deployment | Entry cooldown after exit | **5 s** | an exit was recorded less than 5 s ago | 5 s elapse since the last exit on that deployment |

Semantics:

- "Orders" (per-deployment windows) count entries **and** exits;
  "entries" (fleet-wide windows) count entries only.
- Rate breakers deny **entries only**. Exits are privileged: an exit is
  accepted while every breaker is tripped and the envelope is exhausted.
- All windows are sliding windows over recorded timestamps. The clock is
  injectable, so trip and recovery points are deterministic and tested
  (`tests/risk/test_breakers.py`).

## Envelope semantics

- `max_order_value`: an entry whose notional exceeds the cap is **clamped**
  down to the cap (sign preserved). Clamping only ever shrinks exposure.
  Exits are never clamped.
- `max_daily_loss`: when daily loss (realized + unrealized) reaches the
  cap, the envelope is exhausted and new entries are denied. Exits stay
  privileged. Trips at loss ≥ cap (conservative boundary on money rails).
- Both caps are required `Decimal` fields: constructing an envelope without
  an explicit cap raises `ValidationError`.

## Audit contract

Every firing — a weight clamp, an order-value clamp, a daily-loss denial,
or a breaker denial — writes **exactly one** `ClampEventRow` to the
configured sink: `InMemorySink` for tests, `JsonlSink` for durable audit
(one JSON object per line, append-only).

## License

`limits.py` is vendored verbatim from
[virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) (MIT) at
commit `154a8b2f46dc`; see `LICENSE-ai-hedge-fund` in this directory.
