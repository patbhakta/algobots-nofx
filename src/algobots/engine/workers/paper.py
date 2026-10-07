"""One Nautilus paper worker per demo account (ALG-3255/ALG-3258, A06 slices 1-2).

Run as its own OS process: ``python -m algobots.engine.workers.paper --account laya``.

Each worker owns a Nautilus kernel with a unique trader ID, its own simulated
(paper) venue ``PAPER_<ACCT>`` holding a frozen cash account, and one
strategy whose order-ID tag is the account key. It polls the Laya forward-
observer feed, replays new intervals through ``algobots.demo.ledger`` (so the
risk envelope and kill switch decide exactly as the dashboard shows), and
submits a market order for every FILLED decision on that interval's YES/NO
binary at the 50c paper quote. No live client exists in this process: it
cannot reach a broker.

The ledger stays the P&L source of truth: settlement is not modelled in the
paper venue yet, so the venue account is frozen and positions stay open.
Liveness goes to ``<state_dir>/workers/<account>.json`` every poll.

Ownership and restart (ALG-3258): ``main`` takes the account's lease first
and exits ``EXIT_DENIED`` if another process holds it. A fresh worker is
**entry-frozen**. It reports ``reconciling`` and refuses (and counts) every
entry until ``reconcile()`` has rebuilt the account from durable state: the
ledger replay restores past fills into the paper venue and marks their
intervals done. Only then does it report ``reconciled`` and trade new
intervals. A crashed worker is therefore never resumed straight into trading.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig, StrategyConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, AssetClass, OmsType, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from algobots.demo import killswitch
from algobots.demo import ledger as L
from algobots.engine.workers.lease import EXIT_DENIED, Lease, LeaseDenied

# Nautilus 1.231 calls the deprecated pd.Timestamp.utcnow() on every run().
warnings.filterwarnings("ignore", message="Timestamp.utcnow")

NS = 1_000_000_000


def ids(account: str) -> dict[str, str]:
    """The per-account identity namespace; every ID embeds the account key.

    Nautilus numbers every simulated account ``<venue>-001``, so the venue
    itself carries the account key to keep account and instrument IDs apart.
    """
    tag = account.upper()
    return {
        "trader_id": f"PAPER-{tag}",
        "strategy_id": f"DemoPaper-{tag}",
        "order_id_tag": tag,
        "venue": f"PAPER_{tag}",
        "account_id": f"PAPER_{tag}-001",
    }


def instrument(venue: Venue, event: str, outcome: str, ts: float) -> BinaryOption:
    ts_ns = int(ts * NS)
    return BinaryOption(
        instrument_id=InstrumentId(Symbol(f"{event}-{outcome}"), venue),
        raw_symbol=Symbol(f"{event}-{outcome}"),
        asset_class=AssetClass.CRYPTOCURRENCY,
        currency=USD,
        price_precision=2,
        size_precision=0,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_int(1),
        activation_ns=ts_ns - 900 * NS,
        expiration_ns=ts_ns,
        ts_event=ts_ns,
        ts_init=ts_ns,
        outcome=outcome,
    )


def quote(inst: BinaryOption, ts: float) -> QuoteTick:
    # The PoC feed has no order book: quote the assumed 50c mid both sides,
    # with ample size so a sleeve-capped order always fills in full.
    px, sz, ts_ns = Price.from_str(str(L.FILL_PRICE)), Quantity.from_int(10_000), int(ts * NS)
    return QuoteTick(inst.id, px, px, sz, sz, ts_ns, ts_ns)


class DemoPaperConfig(StrategyConfig, frozen=True):
    account: str = ""


class DemoPaperStrategy(Strategy):
    """Submits the ledger's FILLED decisions as market orders, tagged by account."""

    def __init__(self, config: DemoPaperConfig) -> None:
        super().__init__(config)
        self.account = config.account
        self.pending: dict[InstrumentId, L.Decision] = {}
        self.submitted = 0
        self.filled = 0
        self.restored = 0  # submitted while reconciling, to rebuild venue state
        self.rejected_frozen = 0  # entries refused before reconcile
        self.frozen = True  # no entries until the worker has reconciled
        self.restoring = False
        self.last_order: dict | None = None

    def queue(self, inst_id: InstrumentId, decision: L.Decision) -> bool:
        """Queue an entry for the next quote; refused (and counted) while entry-frozen."""
        if self.frozen and not self.restoring:
            self.rejected_frozen += 1
            return False
        self.pending[inst_id] = decision
        self.subscribe_quote_ticks(inst_id)
        return True

    def on_quote_tick(self, tick: QuoteTick) -> None:
        d = self.pending.pop(tick.instrument_id, None)
        if d is None:
            return
        qty = int(d.stake / L.FILL_PRICE)  # whole contracts at 50c, floored
        order = self.order_factory.market(
            tick.instrument_id,
            OrderSide.BUY,
            Quantity.from_int(qty),
            tags=[f"acct:{self.account}", f"event:{d.event}"],
        )
        self.submit_order(order)
        self.submitted += 1
        self.restored += self.restoring
        self.last_order = {
            "client_order_id": str(order.client_order_id),
            "instrument": str(tick.instrument_id),
            "qty": qty,
            "stake": str(d.stake),
            "ts": d.ts,
        }

    def on_order_filled(self, event) -> None:  # noqa: ANN001 — Nautilus event type
        self.filled += 1


class PaperWorker:
    def __init__(self, account: str, feed: Path, state_dir: Path, start: str, refills: list[float]):
        if account not in L.STRATEGIES:
            raise ValueError(f"unknown demo account {account!r}")
        self.account, self.feed, self.state_dir, self.refills = account, feed, state_dir, refills
        self.since = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
        self.ids = ids(account)
        self.venue = Venue(self.ids["venue"])
        self.started_at = time.time()
        self.ready_at: float | None = None  # reconcile completed
        self.reconciled = False
        self.done_events: set[str] = set()
        self.rows_seen = 0
        self.ran = False  # Nautilus refuses end() on an engine that never ran
        self.engine = BacktestEngine(
            BacktestEngineConfig(
                trader_id=TraderId(self.ids["trader_id"]),
                logging=LoggingConfig(log_level="ERROR"),
            )
        )
        # Paper venue: frozen cash account — the ledger, not the venue, owns P&L.
        self.engine.add_venue(
            self.venue,
            OmsType.NETTING,
            AccountType.CASH,
            [Money(L.SLEEVE, USD)],
            base_currency=USD,
            frozen_account=True,
        )
        self.strategy = DemoPaperStrategy(
            DemoPaperConfig(
                strategy_id=self.ids["strategy_id"],
                order_id_tag=self.ids["order_id_tag"],
                account=account,
            )
        )
        self.engine.add_strategy(self.strategy)
        self.status_path = state_dir / "workers" / f"{account}.json"

    def reconcile(self) -> int:
        """Rebuild the account from the durable ledger, then lift the entry freeze.

        Returns the number of past fills restored into the paper venue.
        """
        self.strategy.restoring = True
        try:
            self.step()
        finally:
            self.strategy.restoring = False
        self.strategy.frozen = False
        self.reconciled = True
        self.ready_at = time.time()
        return self.strategy.restored

    def step(self) -> int:
        """Process feed intervals not yet seen; return how many were new.

        While entry-frozen, a FILLED interval is refused and left unprocessed,
        so ``reconcile()`` restores it from the ledger later.
        """
        rows = L.load_rows(self.feed, since_ts=self.since)
        lg = L.build(rows, killswitch.read(str(self.state_dir)), self.refills)
        new = [d for d in lg.books[self.account].decisions if d.event not in self.done_events]
        ticks = []
        for d in new:
            if d.status != "FILLED":
                self.done_events.add(d.event)
                continue
            inst = instrument(self.venue, d.event, d.side, d.ts)
            if not self.strategy.queue(inst.id, d):
                continue
            self.done_events.add(d.event)
            self.engine.add_instrument(inst)
            ticks.append(quote(inst, d.ts))
        if ticks:
            self.engine.add_data(ticks)
            self.engine.run(streaming=True)
            self.engine.clear_data()
            self.ran = True
        self.rows_seen = len(rows)
        return len(new)

    def heartbeat(self) -> dict:
        s = self.strategy
        status = {
            "account": self.account,
            **self.ids,
            "venue_account_id": str(self.engine.cache.accounts()[0].id)
            if self.engine.cache.accounts()
            else None,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "last_heartbeat": time.time(),
            "ready_at": self.ready_at,
            "phase": "ready" if self.reconciled else "reconciling",
            "reconciled": self.reconciled,
            "intervals": self.rows_seen,
            "orders_submitted": s.submitted,
            "orders_filled": s.filled,
            "orders_restored": s.restored,
            "orders_rejected_frozen": s.rejected_frozen,
            "open_positions": len(self.engine.cache.positions_open()),
            "last_order": s.last_order,
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
    from algobots.api.config import get_settings

    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--account", required=True, choices=sorted(L.STRATEGIES))
    ap.add_argument("--poll", type=float, default=15.0, help="feed poll interval, seconds")
    ap.add_argument("--once", action="store_true", help="process the feed once and exit")
    a = ap.parse_args(argv)
    refills = [
        datetime.strptime(t.strip(), "%Y-%m-%dT%H:%M").replace(tzinfo=UTC).timestamp()
        for t in s.demo_sleeve_refills.split(",")
        if t.strip()
    ]
    lease = Lease(Path(s.demo_state_dir), a.account)
    try:
        lease.acquire()  # a no-op when the supervisor already recorded this PID
    except LeaseDenied as e:
        print(f"denied: {e}", flush=True)
        raise SystemExit(EXIT_DENIED) from None
    w = PaperWorker(
        a.account, Path(s.demo_feed_path), Path(s.demo_state_dir), s.demo_start, refills
    )
    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        w.heartbeat()  # reconciling: entry-frozen
        w.reconcile()
        while True:
            w.step()
            w.heartbeat()
            if a.once or stop:
                break
            deadline = time.monotonic() + a.poll
            while not stop and time.monotonic() < deadline:
                time.sleep(0.2)
    finally:
        w.close()
        lease.release(os.getpid())


if __name__ == "__main__":
    main()
