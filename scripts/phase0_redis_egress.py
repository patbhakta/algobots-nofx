"""Phase 0 P0.3 sandbox node: drive order/position events onto Redis streams.

Runs a self-contained Nautilus backtest node wired to the canonical
`redis_message_bus_config()` egress. The node submits one market order and
then closes the resulting position, so the external streams receive
`OrderInitialized`/`OrderSubmitted`/`OrderFilled` and
`PositionOpened`/`PositionClosed` events. Quote ticks drive the strategy but
are excluded from egress by `types_filter`, which is the behaviour the
`redis-cli XREAD` evidence is meant to demonstrate.

Usage:
    REDIS_HOST=127.0.0.1 REDIS_PORT=16379 python scripts/phase0_redis_egress.py
"""

from __future__ import annotations

import time
from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, StrategyConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.trading.strategy import Strategy

from algobots.engine.redis_message_bus import redis_message_bus_config

VENUE = Venue("SIM")
TRADER_ID = TraderId("ALGOBOTS-001")


class EgressDemoConfig(StrategyConfig, frozen=True):
    """Minimal config for the egress demo strategy."""

    instrument_id: InstrumentId
    trade_size: Decimal


class EgressDemoStrategy(Strategy):
    """Opens one position on the first quote, then closes it on a later quote."""

    def __init__(self, config: EgressDemoConfig) -> None:
        super().__init__(config)
        self.instrument = None
        self._submitted = False
        self._closed = False

    def on_start(self) -> None:
        self.instrument = self.cache.instrument(self.config.instrument_id)
        self.subscribe_quote_ticks(self.config.instrument_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if not self._submitted:
            self._submitted = True
            order = self.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.instrument.make_qty(self.config.trade_size),
            )
            self.submit_order(order)
            return

        if not self._closed and self.portfolio.is_net_long(self.config.instrument_id):
            self._closed = True
            self.close_all_positions(self.config.instrument_id)


def _quote_ticks(instrument_id: InstrumentId, count: int = 8) -> list[QuoteTick]:
    """Synthetic two-sided quotes; no external data dependency."""
    ticks = []
    for i in range(count):
        mid = 1.1000 + (i * 0.0001)
        ts = 1_700_000_000_000_000_000 + (i * 1_000_000_000)
        ticks.append(
            QuoteTick(
                instrument_id=instrument_id,
                bid_price=Price(round(mid - 0.00005, 5), precision=5),
                ask_price=Price(round(mid + 0.00005, 5), precision=5),
                bid_size=Quantity(1_000_000, precision=0),
                ask_size=Quantity(1_000_000, precision=0),
                ts_event=ts,
                ts_init=ts,
            )
        )
    return ticks


def main() -> None:
    instrument = TestInstrumentProvider.default_fx_ccy("EUR/USD", venue=VENUE)

    engine = BacktestEngine(
        config=BacktestEngineConfig(
            trader_id=TRADER_ID,
            message_bus=redis_message_bus_config(),
            logging=LoggingConfig(log_level="WARNING"),
        )
    )
    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        base_currency=USD,
        starting_balances=[Money(1_000_000, USD)],
    )
    engine.add_instrument(instrument)
    engine.add_data(_quote_ticks(instrument.id))
    engine.add_strategy(
        EgressDemoStrategy(
            EgressDemoConfig(
                instrument_id=instrument.id,
                trade_size=Decimal("100_000"),
            )
        )
    )

    engine.run()

    # The message bus writes to Redis on a background interval; give the
    # buffered publish a moment to drain before the process tears it down.
    time.sleep(2)
    engine.dispose()


if __name__ == "__main__":
    main()
