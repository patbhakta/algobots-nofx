"""Nautilus executor for the demo sleeves (ALG-3289).

Every risk-approved entry on a demo sleeve is executed here, on a real
``nautilus_trader`` ``BacktestEngine``: one engine per sleeve, owning a
simulated cash venue ``PAPER_<ACCT>`` funded with the sleeve. For each
interval the sleeve

1. lists the interval's YES/NO contract as a ``BinaryOption`` expiring at
   settlement, with the venue's settlement price set to the observed outcome
   (1.00 if that side won, 0.00 if not);
2. submits a market BUY for whole contracts against the quote, so the
   matching engine fills it and the ``KalshiFeeModel`` charges the taker fee;
3. sends the venue an ``InstrumentClose(CONTRACT_EXPIRED)`` at settlement so
   it closes the position at that settlement price.

The fill price, filled quantity, fee and the cash balance afterwards are all
read back from the engine; ``algobots.demo.ledger`` takes P&L and sleeve
equity from here, never from its own arithmetic.

What is still assumed: the Laya feed records no order book, so the quote the
engine fills against is the 50c mid on both sides (``QUOTE``). Nautilus
executes and accounts; it cannot invent prices the feed never captured.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

import nautilus_trader
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import FeeModel
from nautilus_trader.backtest.modules import SimulationModule, SimulationModuleConfig
from nautilus_trader.config import LoggingConfig, StrategyConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import InstrumentClose, QuoteTick
from nautilus_trader.model.enums import (
    AccountType,
    AssetClass,
    InstrumentCloseType,
    OmsType,
    OrderSide,
)
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TraderId, Venue
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from algobots.demo import ledger as L

# Nautilus 1.231 calls the deprecated pd.Timestamp.utcnow() on every run().
warnings.filterwarnings("ignore", message="Timestamp.utcnow")

NS = 1_000_000_000
INTERVAL_S = 900  # KXBTC15M
QUOTE = L.FILL_PRICE  # the feed records no book: assumed mid, both sides
EXECUTOR = f"NautilusTrader {nautilus_trader.__version__} BacktestEngine"


def kalshi_fee(contracts: Decimal, price: Decimal) -> Decimal:
    """ceil(0.07 * C * P * (1-P)) to the cent, per fill."""
    raw = L.KALSHI_FEE_RATE * contracts * price * (1 - price)
    return raw.quantize(L.CENT, rounding=ROUND_CEILING)


class KalshiFeeModel(FeeModel):
    """Kalshi's taker fee. Settlement fills (P = 0 or 1) cost nothing, as on Kalshi."""

    def get_commission(self, order, fill_qty, fill_px, instrument) -> Money:  # noqa: ANN001
        fee = kalshi_fee(Decimal(str(fill_qty)), Decimal(str(fill_px)))
        return Money(fee, instrument.quote_currency)


class _Treasury(SimulationModule):
    """Holds the venue so sleeve refills credit the Nautilus cash account."""

    def pre_process(self, data) -> None:  # noqa: ANN001
        pass

    def process(self, ts_now: int) -> None:
        pass

    def log_diagnostics(self, logger) -> None:  # noqa: ANN001
        pass

    def reset(self) -> None:
        pass


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
        activation_ns=ts_ns - INTERVAL_S * NS,
        expiration_ns=ts_ns,
        ts_event=ts_ns,
        ts_init=ts_ns,
        outcome=outcome,
    )


def quote(inst_id: InstrumentId, ts: float) -> QuoteTick:
    px, sz, ts_ns = Price.from_str(str(QUOTE)), Quantity.from_int(10_000), int(ts * NS)
    return QuoteTick(inst_id, px, px, sz, sz, ts_ns, ts_ns)


@dataclass(frozen=True)
class Execution:
    """One entry as Nautilus executed and settled it."""

    client_order_id: str
    instrument: str
    qty: int
    price: Decimal  # average fill price
    cost: Decimal  # qty * price
    fee: Decimal  # commission the venue charged
    payout: Decimal  # settlement proceeds
    pnl: Decimal  # cash balance after settlement - before entry
    equity: Decimal  # cash balance after settlement


class SleeveConfig(StrategyConfig, frozen=True):
    account: str = ""


class SleeveStrategy(Strategy):
    """Buys the queued contract count on the next quote for that instrument."""

    def __init__(self, config: SleeveConfig) -> None:
        super().__init__(config)
        self.account = config.account
        self.pending: dict[InstrumentId, tuple[int, str]] = {}
        self.last_order = None
        self.submitted = 0
        self.filled = 0

    def queue(self, inst_id: InstrumentId, qty: int, event: str) -> None:
        self.pending[inst_id] = (qty, event)
        self.subscribe_quote_ticks(inst_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        job = self.pending.pop(tick.instrument_id, None)
        if job is None:
            return
        qty, event = job
        order = self.order_factory.market(
            tick.instrument_id,
            OrderSide.BUY,
            Quantity.from_int(qty),
            tags=[f"acct:{self.account}", f"event:{event}"],
        )
        self.submit_order(order)
        self.submitted += 1
        self.last_order = order

    def on_order_filled(self, event) -> None:  # noqa: ANN001 — Nautilus event type
        if not str(event.client_order_id).startswith("EXPIRATION"):
            self.filled += 1


class NautilusSleeve:
    """One demo sleeve on its own Nautilus engine and simulated cash venue."""

    def __init__(self, account: str, capital: Decimal) -> None:
        self.account = account
        self.ids = ids(account)
        self.venue = Venue(self.ids["venue"])
        self.engine = BacktestEngine(
            BacktestEngineConfig(
                trader_id=TraderId(self.ids["trader_id"]),
                logging=LoggingConfig(log_level="ERROR"),
            )
        )
        # The venue copies a non-empty dict by reference; a placeholder key keeps
        # it non-empty so per-interval outcomes added later reach its matching engines.
        self._settle: dict[InstrumentId, float] = {InstrumentId(Symbol("NONE"), self.venue): 0.0}
        self._treasury = _Treasury(SimulationModuleConfig())
        self.engine.add_venue(
            self.venue,
            OmsType.NETTING,
            AccountType.CASH,
            [Money(capital, USD)],
            base_currency=USD,
            fee_model=KalshiFeeModel(),
            modules=[self._treasury],
            settlement_prices=self._settle,
        )
        self.strategy = SleeveStrategy(
            SleeveConfig(
                strategy_id=self.ids["strategy_id"],
                order_id_tag=self.ids["order_id_tag"],
                account=account,
            )
        )
        self.engine.add_strategy(self.strategy)
        self.ran = False
        self._capital = capital  # cash before the engine first runs

    @property
    def equity(self) -> Decimal:
        acct = self.engine.cache.account_for_venue(self.venue)
        if acct is None:
            return self._capital
        return Decimal(str(acct.balance_total(USD).as_decimal()))

    def top_up(self, amount: Decimal) -> None:
        """Credit added capital to the venue cash account (a refill, not P&L).

        Only a sleeve that lost money needs one, so its engine has already run.
        """
        self._treasury.exchange.adjust_account(Money(amount, USD))

    def execute(self, event: str, side: str, ts: float, won: bool, qty: int) -> Execution:
        """Buy ``qty`` contracts of ``event``'s ``side`` and settle them at ``ts``."""
        before = self.equity
        inst = instrument(self.venue, event, side, ts)
        self._settle[inst.id] = 1.0 if won else 0.0
        self.engine.add_instrument(inst)
        self.strategy.queue(inst.id, qty, event)
        entry_ts = ts - INTERVAL_S + 1
        ts_ns = int(ts * NS)
        close = InstrumentClose(
            inst.id,
            Price.from_str("1.00" if won else "0.00"),
            InstrumentCloseType.CONTRACT_EXPIRED,
            ts_ns,
            ts_ns,
        )
        self.engine.add_data([quote(inst.id, entry_ts), close])
        self.engine.run(streaming=True)
        self.engine.clear_data()
        self.ran = True
        order = self.strategy.last_order
        cache = self.engine.cache
        filled = int(order.filled_qty) if order else 0
        if not order or not order.is_closed or filled != qty:
            raise RuntimeError(f"{self.account} {inst.id}: entry not filled ({order})")
        price = Decimal(str(order.avg_px)).quantize(L.CENT)
        fee = sum((Decimal(str(m.as_decimal())) for m in order.commissions()), Decimal(0))
        settle = [
            o
            for o in cache.orders(instrument_id=inst.id)
            if str(o.client_order_id).startswith("EXPIRATION")
        ]
        if not settle or cache.positions_open(instrument_id=inst.id):
            raise RuntimeError(f"{self.account} {inst.id}: venue did not settle the position")
        payout = Decimal(filled) * Decimal(str(settle[0].avg_px))
        after = self.equity
        return Execution(
            client_order_id=str(order.client_order_id),
            instrument=str(inst.id),
            qty=filled,
            price=price,
            cost=(Decimal(filled) * price).quantize(L.CENT),
            fee=fee.quantize(L.CENT),
            payout=payout.quantize(L.CENT),
            pnl=(after - before).quantize(L.CENT),
            equity=after,
        )

    def close(self) -> None:
        if self.ran:
            self.engine.end()
        self.engine.dispose()
