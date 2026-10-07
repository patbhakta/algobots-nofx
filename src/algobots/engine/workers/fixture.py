"""Declared A06 measurement fixture: a synthetic paper account running two strategies (ALG-3259).

    python -m algobots.engine.workers.fixture --account syn1 --poll 1 --state-dir D

The demo has three ledger-driven accounts, and the A06 workload needs four
with eight deployments. This worker is the declared synthetic stand-in: the
same process shape as ``paper`` (own Nautilus kernel, own paper venue
``PAPER_<ACCT>`` on a frozen cash account, account lease, entry-frozen until
reconciled, heartbeat file), but it is driven by a deterministic synthetic
quote stream instead of the Laya feed. It runs two simple strategies:

* ``EveryN-<ACCT>`` buys 1 contract every ``N``-th quote;
* ``Dip-<ACCT>`` buys 1 contract when the mid drops below 0.45.

Inbound quotes are generated on wall-clock time at ``--rate`` per second per
strategy instrument and wait in a queue until the next poll drains them. The
heartbeat therefore reports real queue depth/age at drain time and the
strategy callback latency (scheduled tick time -> ``on_quote_tick``), next to
the usual order counters. Fills are appended to
``<state>/workers/<acct>.fills.jsonl``. ``reconcile()`` replays that durable
log, so a killed account stays entry-frozen until it has done so.

No live client exists in this process: it cannot reach a broker.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import time
import warnings
from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig, StrategyConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from algobots.engine.workers.lease import EXIT_DENIED, Lease, LeaseDenied
from algobots.engine.workers.paper import NS, ids, instrument

warnings.filterwarnings("ignore", message="Timestamp.utcnow")

FIXTURE_ACCOUNTS = ("syn1", "syn2", "syn3", "syn4")
STRATEGIES_PER_ACCOUNT = 2
EXPIRY_S = 365 * 86400  # synthetic instruments never expire during a run
SAMPLE_CAP = 2000  # latency samples kept per heartbeat window


def pct(xs: list[float], q: float) -> float | None:
    """Nearest-rank percentile, or None without samples."""
    if not xs:
        return None
    s = sorted(xs)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


class FixtureConfig(StrategyConfig, frozen=True):
    account: str = ""
    kind: str = "every_n"  # every_n | dip
    n: int = 20


class FixtureStrategy(Strategy):
    def __init__(self, config: FixtureConfig, worker: FixtureWorker) -> None:
        super().__init__(config)
        self.cfg, self.worker = config, worker
        self.ticks = 0
        self.submitted = 0
        self.filled = 0
        self.inst_id: InstrumentId | None = None

    def on_start(self) -> None:
        if self.inst_id is not None:
            self.subscribe_quote_ticks(self.inst_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        self.worker.latencies_ms.append((time.time() - tick.ts_event / NS) * 1000)
        self.ticks += 1
        mid = (tick.bid_price.as_double() + tick.ask_price.as_double()) / 2
        hit = self.ticks % self.cfg.n == 0 if self.cfg.kind == "every_n" else mid < 0.45
        if not hit:
            return
        if self.worker.frozen:
            self.worker.rejected_frozen += 1
            return
        order = self.order_factory.market(
            tick.instrument_id,
            OrderSide.BUY,
            Quantity.from_int(1),
            tags=[f"acct:{self.cfg.account}", f"strategy:{self.cfg.kind}"],
        )
        self.submit_order(order)
        self.submitted += 1

    def on_order_filled(self, event) -> None:  # noqa: ANN001 — Nautilus event type
        self.filled += 1
        self.worker.log_fill(str(self.id), str(event.client_order_id))


class FixtureWorker:
    def __init__(self, account: str, state_dir: Path, rate: float = 4.0, seed: int = 0) -> None:
        self.account, self.state_dir, self.rate = account, Path(state_dir), rate
        self.ids = ids(account)
        self.venue = Venue(self.ids["venue"])
        self.started_at = time.time()
        self.ready_at: float | None = None
        self.frozen, self.reconciled = True, False
        self.restored = 0
        self.rejected_frozen = 0
        self.latencies_ms: list[float] = []
        self.handler_ms: list[float] = []
        self.queue: list[tuple[float, int]] = []  # (scheduled wall ts, strategy index)
        self.queue_depth: list[int] = []
        self.queue_age_ms: list[float] = []
        self.seq = seed
        self.last_gen = time.time()
        self.ran = False
        self.fills_path = self.state_dir / "workers" / f"{account}.fills.jsonl"
        self.status_path = self.state_dir / "workers" / f"{account}.json"
        self.engine = BacktestEngine(
            BacktestEngineConfig(
                trader_id=TraderId(self.ids["trader_id"]),
                logging=LoggingConfig(log_level="ERROR"),
            )
        )
        self.engine.add_venue(
            self.venue,
            OmsType.NETTING,
            AccountType.CASH,
            [Money(1_000_000, USD)],
            base_currency=USD,
            frozen_account=True,
        )
        tag = self.ids["order_id_tag"]
        self.strategies: list[FixtureStrategy] = []
        self.instruments = []
        for i, kind in enumerate(("every_n", "dip")):
            inst = instrument(self.venue, f"SYN-{tag}-S{i}", "YES", self.started_at + EXPIRY_S)
            self.engine.add_instrument(inst)
            strat = FixtureStrategy(
                FixtureConfig(
                    strategy_id=f"{'EveryN' if kind == 'every_n' else 'Dip'}-{tag}",
                    order_id_tag=f"{tag}{i}",
                    account=account,
                    kind=kind,
                ),
                self,
            )
            strat.inst_id = inst.id
            self.engine.add_strategy(strat)
            self.strategies.append(strat)
            self.instruments.append(inst)

    def log_fill(self, strategy_id: str, client_order_id: str) -> None:
        if self.frozen:  # restoring: the fill is already in the durable log
            return
        with self.fills_path.open("a") as fh:
            fh.write(json.dumps({"strategy": strategy_id, "order": client_order_id}) + "\n")

    def reconcile(self) -> int:
        """Replay the durable fill log, then lift the entry freeze; returns fills restored."""
        try:
            self.restored = sum(1 for _ in self.fills_path.open())
        except FileNotFoundError:
            self.restored = 0
        self.frozen, self.reconciled, self.ready_at = False, True, time.time()
        return self.restored

    def _mid(self, seq: int) -> float:
        return round(0.5 + 0.08 * math.sin(seq / 7.0), 2)  # 0.42..0.58, deterministic

    def generate(self, now: float | None = None) -> None:
        """Enqueue the quotes that came due since the last call (wall-clock scheduled)."""
        now = time.time() if now is None else now
        step = 1.0 / self.rate
        t = self.last_gen + step
        while t <= now:
            for i in range(len(self.strategies)):
                self.queue.append((t, i))
            t += step
        self.last_gen = t - step

    def step(self) -> int:
        """Drain the inbound queue through the engine; returns ticks processed."""
        self.generate()
        if not self.queue:
            return 0
        now = time.time()
        self.queue_depth.append(len(self.queue))
        self.queue_age_ms.append((now - self.queue[0][0]) * 1000)
        ticks = []
        for ts, i in self.queue:
            self.seq += 1
            px = Price.from_str(f"{self._mid(self.seq):.2f}")
            sz, ts_ns = Quantity.from_int(10_000), int(ts * NS)
            ticks.append(QuoteTick(self.instruments[i].id, px, px, sz, sz, ts_ns, ts_ns))
        self.queue.clear()
        ticks.sort(key=lambda q: q.ts_init)
        t0 = time.perf_counter()
        self.engine.add_data(ticks)
        self.engine.run(streaming=True)
        self.engine.clear_data()
        self.handler_ms.append((time.perf_counter() - t0) * 1000 / len(ticks))
        self.ran = True
        return len(ticks)

    def heartbeat(self) -> dict:
        lat = self.latencies_ms[-SAMPLE_CAP:]
        del self.latencies_ms[:-SAMPLE_CAP]
        status = {
            "account": self.account,
            **self.ids,
            "fixture": "synthetic-2-strategy",
            "strategies": [str(s.id) for s in self.strategies],
            "pid": os.getpid(),
            "uid": os.getuid(),
            "started_at": self.started_at,
            "last_heartbeat": time.time(),
            "ready_at": self.ready_at,
            "phase": "ready" if self.reconciled else "reconciling",
            "reconciled": self.reconciled,
            "intervals": sum(s.ticks for s in self.strategies),
            "orders_submitted": sum(s.submitted for s in self.strategies),
            "orders_filled": sum(s.filled for s in self.strategies),
            "orders_restored": self.restored,
            "orders_rejected_frozen": self.rejected_frozen,
            "open_positions": len(self.engine.cache.positions_open()),
            "callback_latency_ms": {"p50": pct(lat, 50), "p95": pct(lat, 95), "n": len(lat)},
            "per_tick_engine_ms_p95": pct(self.handler_ms[-SAMPLE_CAP:], 95),
            "queue_depth": {
                "p50": pct(self.queue_depth, 50),
                "p95": pct(self.queue_depth, 95),
                "max": max(self.queue_depth, default=None),
            },
            "queue_age_ms": {
                "p50": pct(self.queue_age_ms, 50),
                "p95": pct(self.queue_age_ms, 95),
                "max": max(self.queue_age_ms, default=None),
            },
            "latency_samples_ms": [round(x, 3) for x in lat[-500:]],
            "mode": "paper",
        }
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status))
        tmp.replace(self.status_path)
        return status

    def close(self) -> None:
        if self.ran:
            self.engine.end()
        self.engine.dispose()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--account", required=True)
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--rate", type=float, default=4.0, help="quotes/s per strategy instrument")
    ap.add_argument("--state-dir", default=os.environ.get("ALGOBOTS_DEMO_STATE_DIR", "."))
    a = ap.parse_args(argv)
    lease = Lease(Path(a.state_dir), a.account)
    try:
        lease.acquire()
    except LeaseDenied as e:
        print(f"denied: {e}", flush=True)
        raise SystemExit(EXIT_DENIED) from None
    w = FixtureWorker(a.account, Path(a.state_dir), rate=a.rate)
    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        w.heartbeat()  # reconciling: entry-frozen
        w.reconcile()
        w.last_gen = time.time()  # the stream starts once the account is live
        while not stop:
            deadline = time.monotonic() + a.poll
            while not stop and time.monotonic() < deadline:
                time.sleep(0.05)
            w.step()
            w.heartbeat()
    finally:
        w.close()
        lease.release(os.getpid())


if __name__ == "__main__":
    main()
