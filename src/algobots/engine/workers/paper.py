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

Execution seam (ALG-3270): the execution client comes from the account's
``AccountWorkerSpec``. ``sandbox`` is the simulated venue above and the
default. ``adapter:<name>`` selects a shipped Nautilus adapter, and this worker
refuses it until a broker connection is authorized (see ``execution``). The
refusal exits ``EXIT_REFUSED`` (77), distinct from the lease denial's
``EXIT_DENIED`` (75), so the supervisor reports it ``exited``, not ``denied``. Fills
are recorded from Nautilus ``OrderFilled`` events (``strategy.fills``), not
read back from the ledger. ``reconcile_fills`` diffs them against the ledger.

Order API (ALG-3263): ``drain_api_orders`` claims this account's inbox
(``workers/<account>.inbox.jsonl``, written by ``demo.orderapi`` after the
shared risk gate) and executes every still-``submitted`` leg on this worker's
Nautilus engine, appending a ``fill`` record (this trader's identity on it)
to the ticket journal. Fills are final; a leg cancelled first is dropped.
Every heartbeat also carries a ``report``: funds and open positions as this
worker computes them — the v1 read endpoints serve nothing else.

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
import fcntl
import json
import os
import signal
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig, StrategyConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, AssetClass, OmsType, OrderSide
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    Symbol,
    TraderId,
    Venue,
)
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from algobots.demo import blotter as B
from algobots.demo import killswitch
from algobots.demo import ledger as L
from algobots.engine.workers.execution import (
    EXIT_REFUSED,
    AccountWorkerSpec,
    AdapterNotAuthorized,
    adapter_node_config,
    specs,
)
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


def quote(inst: BinaryOption, ts: float, px: Decimal = L.FILL_PRICE) -> QuoteTick:
    # Quote the decision's executable price both sides (the ledger fills at
    # the recorded book ask), with ample size so the order fills in full.
    q, sz, ts_ns = Price.from_str(str(px)), Quantity.from_int(10_000), int(ts * NS)
    return QuoteTick(inst.id, q, q, sz, sz, ts_ns, ts_ns)


def current_event(now: float) -> str:
    """The KXBTC15M interval id an entry at ``now`` trades (same ticker format)."""
    slot = datetime.fromtimestamp(int(now // 900) * 900, UTC)
    return f"{B.INSTRUMENT}-{slot.strftime('%y%b%d%H%M').upper()}"


def event_ts(event_id: str, fallback: float) -> float:
    """When ``<prefix>-<yyMonddHHMM>`` settles (``ledger.interval_ts`` twin)."""
    try:
        return (
            datetime.strptime(event_id.split("-")[1], "%y%b%d%H%M").replace(tzinfo=UTC).timestamp()
        )
    except (IndexError, ValueError):
        return fallback


@dataclass
class ApiOrder:
    """A gated order-api request riding the same queue path as a decision."""

    req: dict
    event: str  # interval id the contract belongs to
    ts: float
    stake: Decimal
    sell: bool = False  # kind == exit: sell the contracts back at the mid
    qty: int | None = None  # fixed size (position close); entries size from the stake
    done: bool = False  # an OrderFilled event landed for it


@dataclass
class BridgeOrder:
    """An admitted bridge intent (ALG-3340) riding the same queue path.

    The control plane already ran admission (scope, PAPER-only, gate); this
    worker executes it on its Nautilus engine and mirrors the OrderFilled
    event back to the bridge channel.
    """

    intent: dict
    event: str  # interval id the contract belongs to
    ts: float
    qty: int  # whole contracts (admission already clamped the value)
    sell: bool  # side == sell: exit the contracts at the mid


class DemoPaperConfig(StrategyConfig, frozen=True):
    account: str = ""


class DemoPaperStrategy(Strategy):
    """Submits the ledger's FILLED decisions (and order-api legs) as market orders."""

    def __init__(self, config: DemoPaperConfig) -> None:
        super().__init__(config)
        self.account = config.account
        self.pending: dict[InstrumentId, list[L.Decision | ApiOrder | BridgeOrder]] = {}
        self.submitted = 0
        self.filled = 0
        self.restored = 0  # submitted while reconciling, to rebuild venue state
        self.rejected_frozen = 0  # entries refused before reconcile
        self.frozen = True  # no entries until the worker has reconciled
        self.restoring = False
        self.last_order: dict | None = None
        # client_order_id -> the decision / api leg / bridge intent it executes
        self.decision_for: dict[str, L.Decision | ApiOrder | BridgeOrder] = {}
        self.fills: list[dict] = []  # one per Nautilus OrderFilled event
        self.api_pending: dict[str, ApiOrder] = {}  # client_order_id -> not-yet-filled api leg
        self.api_filled = 0
        self.api_rejected = 0
        self.api_sink: Callable | None = None  # worker hook: (OrderFilled, ApiOrder) -> None
        self.bridge_pending: dict[str, BridgeOrder] = {}  # client_order_id -> claimed bridge intent
        self.bridge_filled = 0
        self.bridge_sink: Callable | None = None  # worker hook: (OrderFilled, BridgeOrder) -> None

    @property
    def accepting(self) -> bool:
        return self.restoring or not self.frozen

    def queue(self, inst_id: InstrumentId, order: L.Decision | ApiOrder | BridgeOrder) -> bool:
        """Queue an entry for the next quote; refused (and counted) while entry-frozen.

        Several orders can ride one instrument (a split's clips all trade the
        same interval contract): the queue is a list per instrument.
        """
        if not self.accepting:
            self.rejected_frozen += 1
            return False
        self.pending.setdefault(inst_id, []).append(order)
        self.subscribe_quote_ticks(inst_id)
        return True

    def on_quote_tick(self, tick: QuoteTick) -> None:
        for d in self.pending.pop(tick.instrument_id, []):
            if isinstance(d, BridgeOrder):
                qty, sell = d.qty, d.sell
                tags = [f"acct:{self.account}", f"event:{d.event}",
                        f"intent:{d.intent.get('intent_id')}"]
            elif isinstance(d, ApiOrder):
                qty = d.qty if d.qty else int(d.stake / L.FILL_PRICE)
                sell = d.sell
                tags = [f"acct:{self.account}", f"event:{d.event}", f"api:{d.req['leg_id']}"]
            else:  # L.Decision: the ledger already sized qty at its fill price
                qty, sell, tags = d.qty or int(d.stake / L.FILL_PRICE), False, [
                    f"acct:{self.account}",
                    f"event:{d.event}",
                ]
            order = self.order_factory.market(
                tick.instrument_id,
                OrderSide.SELL if sell else OrderSide.BUY,
                Quantity.from_int(qty),
                tags=tags,
            )
            self.decision_for[str(order.client_order_id)] = d
            if isinstance(d, ApiOrder):
                self.api_pending[str(order.client_order_id)] = d
            elif isinstance(d, BridgeOrder):
                self.bridge_pending[str(order.client_order_id)] = d
            self.submit_order(order)
            self.submitted += 1
            self.restored += self.restoring
            self.last_order = {
                "client_order_id": str(order.client_order_id),
                "instrument": str(tick.instrument_id),
                "qty": qty,
                "stake": None if isinstance(d, BridgeOrder) else str(d.stake),
                "ts": d.ts,
            }

    def on_order_filled(self, event) -> None:  # noqa: ANN001 — Nautilus OrderFilled
        d = self.decision_for.get(str(event.client_order_id))
        self.fills.append(
            {
                "client_order_id": str(event.client_order_id),
                "trade_id": str(event.trade_id),
                "account_id": str(event.account_id),
                "instrument": str(event.instrument_id),
                "event": d.event if d else None,
                "qty": str(event.last_qty),
                "px": str(event.last_px),
                "commission": str(event.commission),
                "ts_event": event.ts_event,
            }
        )
        self.filled += 1
        if isinstance(d, ApiOrder):
            d.done = True
            self.api_pending.pop(str(event.client_order_id), None)
            self.api_filled += 1
            if self.api_sink is not None:
                self.api_sink(event, d)
        elif isinstance(d, BridgeOrder):
            self.bridge_pending.pop(str(event.client_order_id), None)
            self.bridge_filled += 1
            if self.bridge_sink is not None:
                self.bridge_sink(event, d)


def strategy_kwargs(account: str) -> dict[str, str]:
    """``DemoPaperConfig`` kwargs. Both execution paths use these unchanged."""
    i = ids(account)
    return {
        "strategy_id": i["strategy_id"],
        "order_id_tag": i["order_id_tag"],
        "account": account,
    }


def node_config(spec: AccountWorkerSpec):
    """The ``TradingNodeConfig`` an adapter spec would run. Builds config only, connects nothing."""
    return adapter_node_config(spec, ids(spec.account)["trader_id"], strategy_kwargs(spec.account))


class PaperWorker:
    def __init__(
        self,
        account: str,
        feed: Path,
        state_dir: Path,
        start: str,
        refills: list[float],
        spec: AccountWorkerSpec | None = None,
        bridge_dir: Path | None = None,
    ):
        if account not in L.STRATEGIES:
            raise ValueError(f"unknown demo account {account!r}")
        self.spec = spec or AccountWorkerSpec(account)
        if self.spec.account != account:
            raise ValueError(f"spec is for {self.spec.account!r}, not {account!r}")
        if self.spec.adapter is not None:
            a = self.spec.adapter
            raise AdapterNotAuthorized(
                f"{account}: {self.spec.execution} would connect a {a.venue} account, an "
                f"external mutation that A06 has not authorized. Needs {', '.join(a.credentials)}; "
                f"{a.infra}"
            )
        self.account, self.feed, self.state_dir, self.refills = account, feed, state_dir, refills
        self.bridge = bridge_dir  # ALG-3340: shared channel dir, or None (bridge off)
        self.since = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()
        self.ids = ids(account)
        self.venue = Venue(self.ids["venue"])
        self.started_at = time.time()
        self.ready_at: float | None = None  # reconcile completed
        self.reconciled = False
        self.done_events: set[str] = set()
        self.rows_seen = 0
        self.ran = False  # Nautilus refuses end() on an engine that never ran
        self.last_book: L.StrategyBook | None = None  # latest ledger build for this account
        self.api_inbox = state_dir / "workers" / f"{account}.inbox.jsonl"
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
        self.strategy = DemoPaperStrategy(DemoPaperConfig(**strategy_kwargs(account)))
        self.strategy.api_sink = self._record_api_fill
        self.strategy.bridge_sink = self._record_bridge_fill
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
        self.last_book = lg.books[self.account]
        new = [d for d in lg.books[self.account].decisions if d.event not in self.done_events]
        ticks = []
        for d in new:
            if d.status != "FILLED":
                self.done_events.add(d.event)
                continue
            inst = instrument(self.venue, d.event, d.side, d.ts)
            if self.strategy.accepting:  # the instrument must exist before the subscribe
                self.engine.add_instrument(inst)
            if not self.strategy.queue(inst.id, d):
                continue
            self.done_events.add(d.event)
            ticks.append(
                quote(inst, d.ts, d.price if d.price > 0 else L.FILL_PRICE)
            )
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
            "fill_events": len(s.fills),
            "last_fill": s.fills[-1] if s.fills else None,
            "orders_restored": s.restored,
            "orders_rejected_frozen": s.rejected_frozen,
            "api_orders_filled": s.api_filled,
            "api_orders_rejected": s.api_rejected,
            "bridge_fills": s.bridge_filled,
            "bridge_pending": len(s.bridge_pending),
            "open_positions": len(self.engine.cache.positions_open()),
            "last_order": s.last_order,
            "mode": "paper",
            "execution": self.spec.execution,
            "report": self.report(),
        }
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status))
        tmp.replace(self.status_path)
        return status

    def report(self) -> dict:
        """Funds and open positions as THIS worker computes them (v1 reads)."""
        from algobots.demo import tickets as TK

        def _d(x) -> str:  # noqa: ANN001 — Money/Price/Quantity -> plain decimal string
            return str(x.as_decimal()) if hasattr(x, "as_decimal") else str(x)

        legs = [
            x
            for p in TK.load(str(self.state_dir))
            for x in p.legs
            if x.account == self.account and x.worker_order_id
        ]
        api_fees = sum((Decimal(x.fee) for x in legs), Decimal(0))
        entries = sum((Decimal(x.notional) for x in legs if x.kind == "entry"), Decimal(0))
        exits = sum((Decimal(x.notional) for x in legs if x.kind == "exit"), Decimal(0))
        book = self.last_book
        accounts = self.engine.cache.accounts()
        balance = _d(accounts[0].balance_total(USD)) if accounts else None
        return {
            "funds": {
                "currency": "USD",
                "venue_balance": balance,  # frozen: the ledger owns P&L, the venue holds cash
                "allocated": str(book.allocated) if book else str(L.SLEEVE),
                "equity": str((book.equity if book else L.SLEEVE) - api_fees),
                "strategy_pnl": str(book.pnl) if book else "0",
                "api_fees_paid": str(api_fees),
                "api_open_notional": str(max(Decimal(0), entries - exits)),
                "open_positions": len(self.engine.cache.positions_open()),
            },
            "positions": [
                {
                    "symbol": str(p.instrument_id.symbol),
                    "venue": str(p.instrument_id.venue),
                    "instrument": str(p.instrument_id),
                    "side": p.side.name if hasattr(p.side, "name") else str(p.side),
                    "qty": _d(p.quantity),
                    "avg_price": _d(p.avg_px_open),
                    "opened_ts": (p.ts_opened / NS) if p.ts_opened else None,
                    "unrealized_pnl": None,  # no quotes are captured: nothing to mark against
                }
                for p in self.engine.cache.positions_open()
            ],
        }

    # --- order API (ALG-3263): execute the API's gated legs on this worker ------------------

    def _record_api_fill(self, event, order: ApiOrder) -> None:  # noqa: ANN001 — OrderFilled
        """Append the worker-executed fill to the ticket journal (identity on it)."""
        from algobots.demo import tickets as TK

        qty, px = Decimal(str(event.last_qty)), Decimal(str(event.last_px))
        TK.append_event(
            str(self.state_dir),
            {
                "rec": "fill",
                "parent": order.req["parent_id"],
                "leg": order.req["leg_id"],
                "ts": time.time(),
                "qty": str(qty),
                "price": str(px),
                "notional": str((qty * px).quantize(L.CENT)),
                "fee": str(L.fee_for((qty * px).quantize(L.CENT))),
                "trader_id": self.ids["trader_id"],
                "order_id_tag": self.ids["order_id_tag"],
                "client_order_id": str(event.client_order_id),
                "trade_id": str(event.trade_id),
                "venue_account_id": str(event.account_id),
                "instrument": str(event.instrument_id),
            },
        )

    def _record_api_reject(self, req: dict, reason: str) -> None:
        from algobots.demo import tickets as TK

        self.strategy.api_rejected += 1
        TK.append_event(
            str(self.state_dir),
            {"rec": "reject", "parent": req["parent_id"], "leg": req["leg_id"], "reason": reason},
        )

    def _claim_inbox(self) -> list[dict]:
        """Atomically take every queued request: API appends under the same lock."""
        try:
            with open(self.api_inbox.with_suffix(".lock"), "a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    text = self.api_inbox.read_text() if self.api_inbox.exists() else ""
                    self.api_inbox.write_text("")
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            try:
                req = json.loads(line)
                if isinstance(req, dict) and req.get("leg_id") and req.get("parent_id"):
                    out.append(req)
            except ValueError:
                continue
        return out

    def drain_api_orders(self) -> list[dict]:
        """Execute every still-submitted API leg on this worker's Nautilus engine.

        A leg cancelled (or already filled) is dropped, never executed twice;
        a request the journal no longer knows is dropped with a reject record.
        Entry-frozen workers leave their inbox untouched for after reconcile.
        """
        from algobots.demo import tickets as TK

        if not self.reconciled:
            return []
        reqs = self._claim_inbox()
        if not reqs:
            return []
        now = time.time()
        parents = {p.id: p for p in TK.load(str(self.state_dir))}
        executed: list[dict] = []
        ticks: dict[str, BinaryOption] = {}
        for req in reqs:
            parent = parents.get(req.get("parent_id"))
            leg = (
                next((x for x in parent.legs if x.id == req.get("leg_id")), None)
                if parent
                else None
            )
            if leg is not None and leg.account != self.account:
                continue  # misrouted: another worker owns it
            if leg is None:
                self._record_api_reject(req, "journal no longer knows this leg")
                continue
            if leg.status != "submitted":
                continue  # cancelled first, or already filled: fills are final
            try:
                notional = Decimal(str(req.get("notional", "0")))
                if notional <= 0:
                    raise InvalidOperation
            except InvalidOperation:
                self._record_api_reject(req, "notional must be > 0 USD")
                continue
            symbol = req.get("symbol") or f"{current_event(now)}-{leg.side}"
            event_id, _, outcome = str(symbol).rpartition("-")
            inst_id = InstrumentId(Symbol(str(symbol)), self.venue)
            inst = self.engine.cache.instrument(inst_id)
            if inst is None:
                inst = instrument(self.venue, event_id, outcome.upper(), event_ts(event_id, now))
                self.engine.add_instrument(inst)
            order = ApiOrder(
                req=req,
                event=event_id,
                ts=now,
                stake=notional,
                sell=leg.kind == "exit",
                qty=int(req["qty"]) if req.get("qty") else None,
            )
            if not self.strategy.queue(inst_id, order):
                raise RuntimeError("reconciled worker refused an api entry")  # unreachable
            ticks[str(symbol)] = inst
            executed.append(req)
        if ticks:
            self.engine.add_data([quote(inst, now) for inst in ticks.values()])
            self.engine.run(streaming=True)
            self.engine.clear_data()
            self.ran = True
            for oid, order in list(self.strategy.api_pending.items()):
                venue_order = self.engine.cache.order(ClientOrderId(oid))
                why = (
                    f"venue left it {venue_order.status}"
                    if venue_order is not None
                    else "venue order not found"
                )
                self._record_api_reject(order.req, why)
            self.strategy.api_pending.clear()
        return executed

    # --- bridge (ALG-3340): execute admitted intents on this worker --------------------------

    def _record_bridge_fill(self, event, order: BridgeOrder) -> None:  # noqa: ANN001 — OrderFilled
        """Mirror the Nautilus OrderFilled to bridge/fills/ and finish the intent."""
        from algobots.bridge import channel as CH

        qty, px = Decimal(str(event.last_qty)), Decimal(str(event.last_px))
        ts_utc = (
            datetime.fromtimestamp(event.ts_event / NS, UTC).isoformat() if event.ts_event else None
        )
        fill = {
            "schema": "bridge-fill/1",
            "intent_id": order.intent.get("intent_id"),
            "account": self.account,
            "symbol": str(event.instrument_id.symbol),
            "side": order.intent.get("side"),
            "qty": str(qty),
            "px": str(px),
            "notional": str((qty * px).quantize(L.CENT)),
            "commission": str(event.commission),
            "client_order_id": str(event.client_order_id),
            "trade_id": str(event.trade_id),
            "trader_id": self.ids["trader_id"],
            "order_id_tag": self.ids["order_id_tag"],
            "venue": self.ids["venue"],
            "venue_account_id": str(event.account_id),
            "ts_event": event.ts_event,
            "ts_utc": ts_utc,
            "ts_recorded": time.time(),
        }
        CH.append_fill(self.bridge, self.account, fill)
        CH.finish_intent(
            self.bridge,
            self.account,
            str(order.intent.get("intent_id")),
            {
                "status": "filled",
                "finished_ts": time.time(),
                "fill": {
                    "trade_id": fill["trade_id"],
                    "client_order_id": fill["client_order_id"],
                    "qty": fill["qty"],
                    "px": fill["px"],
                    "ts_utc": fill["ts_utc"],
                },
            },
        )

    def _reject_bridge(self, intent: dict, reason: str) -> None:
        from algobots.bridge import channel as CH

        CH.finish_intent(
            self.bridge,
            self.account,
            str(intent.get("intent_id")),
            {"status": "rejected", "reason": reason, "finished_ts": time.time()},
        )

    def drain_bridge_intents(self) -> list[dict]:
        """Execute every claimed bridge intent on this worker's Nautilus engine.

        Claims are atomic renames (``intents/`` -> ``processing/<account>/``);
        a claim that survives a crash is replayed on the next drain
        (at-least-once — fill records carry ``intent_id`` for dedupe). Every
        claimed intent reaches a terminal outcome: a fill mirrors its
        OrderFilled to ``fills/<account>.jsonl``; anything the venue left
        unfilled is rejected with the venue's own status. Entry-frozen
        workers leave the channel untouched for after reconcile.
        """
        from algobots.bridge import channel as CH

        if self.bridge is None or not self.reconciled:
            return []
        intents, malformed = CH.claim_intents(self.bridge, self.account)
        for path in malformed:
            CH.reject_malformed(self.bridge, path, "intent file is not a JSON object")
        if not intents:
            return []
        now = time.time()
        ticks: dict[str, BinaryOption] = {}
        for it in intents:
            try:
                symbol = str(it.get("symbol") or f"{current_event(now)}-YES")
                event_id, _, outcome = symbol.rpartition("-")
                qty = int(it["qty"])
                if not event_id or not outcome or qty < 1:
                    raise ValueError
                sell = str(it.get("side", "buy")).lower() == "sell"
            except (KeyError, TypeError, ValueError):
                self._reject_bridge(it, "intent fields invalid after admission")
                continue
            inst_id = InstrumentId(Symbol(symbol), self.venue)
            inst = self.engine.cache.instrument(inst_id)
            if inst is None:
                inst = instrument(self.venue, event_id, outcome.upper(), event_ts(event_id, now))
                self.engine.add_instrument(inst)
            order = BridgeOrder(intent=it, event=event_id, ts=now, qty=qty, sell=sell)
            if not self.strategy.queue(inst_id, order):
                raise RuntimeError("reconciled worker refused a bridge entry")  # unreachable
            ticks[symbol] = inst
        if ticks:
            self.engine.add_data([quote(inst, now) for inst in ticks.values()])
            self.engine.run(streaming=True)
            self.engine.clear_data()
            self.ran = True
            for oid, order in list(self.strategy.bridge_pending.items()):
                venue_order = self.engine.cache.order(ClientOrderId(oid))
                why = (
                    f"venue left it {venue_order.status}"
                    if venue_order is not None
                    else "venue order not found"
                )
                self._reject_bridge(order.intent, why)
            self.strategy.bridge_pending.clear()
        return intents

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
    ap.add_argument(
        "--execution", help="'sandbox' or 'adapter:<name>' (default: $ALGOBOTS_WORKER_EXECUTION)"
    )
    ap.add_argument(
        "--bridge",
        help="bridge channel dir to drain intents from (default: $ALGOBOTS_BRIDGE_DIR)",
    )
    a = ap.parse_args(argv)
    spec = (
        AccountWorkerSpec(a.account, a.execution)
        if a.execution
        else specs(sorted(L.STRATEGIES))[a.account]
    )
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
    try:
        bridge = Path(a.bridge) if a.bridge else (Path(s.bridge_dir) if s.bridge_dir else None)
        w = PaperWorker(
            a.account,
            Path(s.demo_feed_path),
            Path(s.demo_state_dir),
            s.demo_start,
            refills,
            spec,
            bridge_dir=bridge,
        )
    except AdapterNotAuthorized as e:
        lease.release(os.getpid())
        print(f"refused: {e}", flush=True)
        raise SystemExit(EXIT_REFUSED) from None
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
            w.drain_api_orders()
            w.drain_bridge_intents()
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
