# Gate G1 — Phase 1 end-to-end paper order (ROADMAP-v3, ALG-3373)

> Not the same gate as `docs/gates/G1/decision.md`. That one is the previous
> roadmap's five-capability paper demo (A12, ALG-3257). This is ROADMAP-v3's
> Phase 1 gate: one order, one fill, one latency budget.

**The claim:** a market order placed in NoFX reaches the sandbox through the
gateway, fills, and the fill is visible in NoFX **within 2 seconds** — and that
test runs in CI on every merge.

**Status: passing.** Measured **0.072 s in CI** and 0.081–0.090 s on `.243`,
against real Postgres and real Redis; the budget is 2.000 s — roughly 28x
headroom. The measurement is written to `artifacts/ALG-3373/g1-latency.json` on
every run and uploaded as a CI artifact (`gate-g1-latency`).

First green CI run:
[`gate-g1` @ 38650219676](https://github.com/patbhakta/algobots/actions/runs/38650219676/job/116146874872)
(commit `36754e1`, PR [#6](https://github.com/patbhakta/algobots/pull/6)).

## How to run it

```sh
POSTGRES_PASSWORD=... docker compose up -d postgres redis   # Phase 0 services

ALGOBOTS_GATEWAY_TEST_PG_URL=postgresql+psycopg://algobots:...@127.0.0.1:5432/algobots \
ALGOBOTS_TEST_REDIS_URL=redis://127.0.0.1:6379/0 \
  make verify-G1
```

CI runs the same script in the `gate-g1` job (`.github/workflows/ci.yml`),
against service containers, on every pull request and every push to `main`.

## What is measured

The clock starts when `POST /v1/orders` returns and stops when
`GET /v1/orders/{clientOrderId}` first reports `filled`. Between those two
points:

| Hop | Code | Real? |
| --- | --- | --- |
| `POST /v1/orders` | `gateway/app.py` over uvicorn | real HTTP |
| admission: scope, shape, PAPER-only, node fitness | `gateway/admission.py` | real |
| `algobots:cmd:<node>` | `gateway/nodes.py::RedisCommandBus` | **real Redis** |
| consumer-group read | `node/command_stream.py` | real |
| dedupe, one venue call | `node/command_actor.py` | real |
| the venue | `node/sandbox.py` | **fixture** |
| `trader-*:algobots:events.*` | `node/event_egress.py` | **real Redis** |
| read, decode, fold | `gateway/event_ingest.py` | real |
| Nautilus wire shapes | `gateway/node_events.py` | real |
| orders / fills / positions | `gateway/store.py::SqlProjection` | **real Postgres** |
| `GET /v1/orders/{id}` | `gateway/app.py` | real HTTP |

The client leg is the request `clients/gateway/client.gen.go` makes — the same
path, headers and bearer. NoFX's `nautilus` exchange (ALG-3372, verified by
`go test ./trader/nautilus` in the fork) calls that generated client, so the
gate drives the HTTP surface NoFX drives.

## What is *not* covered

Two things, named rather than implied:

1. **`node/nautilus_actor.py`** — turning a `SubmitOrder` into an engine order.
   CI installs the `dev` extra and `nautilus_trader` lives in `workers`, so the
   gate cannot import it. It is covered by `tests/node` against the engine's
   API and by `scripts/phase0_redis_egress.py` against a real node; the event
   shapes this gate carries are that node's own capture
   (`artifacts/ALG-3350/p03-redis-xread-evidence.md`).
2. **Matching and pricing.** The sandbox decides no price — `fill_px` is
   supplied by the harness. The gate asserts the gateway reports *that* number,
   which is only meaningful because nothing on the path is allowed to invent
   one.

## Why a skipped gate fails

`tests/e2e` skips without its two services, and a skipped test is a green test.
Phase 2 and the P6.2 signal service both start on the strength of this gate
passing, so two things guard against it silently going grey:

- `scripts/verify_g1.py` exits non-zero when no measurement was written, which
  is what a skip produces.
- `tests/e2e/test_g1_ci_wiring.py` asserts the `gate-g1` job still exists, with
  both service containers, both environment variables, the `postgres` extra,
  the verify script, and the artifact upload. Removing any of them is a test
  failure in the ordinary `pytest` job.

## What G1 unblocks

Per ROADMAP-v3: Phase 2 (friends-and-family login) and P6.2 (the `signals`
service). Phase 4 prediction-market work still waits for G3.

## Beyond the gate

Two further assertions run in the same job, because the stack is already up and
they are the properties a member actually depends on:

- the fill is also **pushed** on `ws /v1/events` with a `seq` after the
  subscriber's cursor, and delivered once;
- the same order submitted twice under one `Idempotency-Key` is answered `200`
  with the first order, executes once at the venue, and leaves one fill and one
  position — the leg that makes a NoFX retry safe.
