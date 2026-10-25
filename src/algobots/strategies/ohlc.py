"""Daily cash-equity DSL replay on quantlab's pinned Nautilus rc6 engine."""

from __future__ import annotations

from decimal import Decimal
from importlib.metadata import version

from algobots.strategies.dsl import min_warmup, validate_spec
from algobots.strategies.eval import Bar as EvalBar
from algobots.strategies.eval import evaluate


def run(artifact, manifest, rows):
    from nautilus_trader.backtest import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig, StrategyConfig
    from nautilus_trader.execution import FixedFeeModel
    from nautilus_trader.model import (
        AccountType,
        Bar,
        BarType,
        Currency,
        Equity,
        InstrumentId,
        Money,
        OmsType,
        OrderSide,
        Price,
        Quantity,
        StrategyId,
        Symbol,
        Venue,
    )
    from nautilus_trader.trading import Strategy

    if version("nautilus_trader") != "2.0.0rc6":
        raise ValueError("OHLC replay requires Nautilus 2.0.0rc6")
    spec = validate_spec(artifact["spec"])
    identity = manifest["instrument_id"]
    if artifact["implementation"] != "condition_dsl.v1":
        raise ValueError("OHLC replay requires condition_dsl.v1")
    if artifact["nautilus"]["instrument_ids"] != [identity] or spec.cadence != "1d":
        raise ValueError("select one matching instrument and daily cadence")
    if manifest.get("dataset") != "openbb-spy-daily" or identity != "SPY.NYSE":
        raise ValueError("OHLC executor currently supports OpenBB SPY daily cash equities")
    warmup = max(min_warmup(spec), spec.warmup_bars or 0)
    if len(rows) <= warmup:
        raise ValueError("snapshot needs warmup bars and at least one execution bar")
    usd = Currency.from_str("USD")
    instrument = Equity(
        instrument_id=InstrumentId.from_str(identity),
        raw_symbol=Symbol("SPY"),
        currency=usd,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
    bar_type = BarType.from_str(f"{identity}-1-DAY-LAST-EXTERNAL")
    bars = [
        Bar(
            bar_type,
            *[Price.from_str(f"{r[k]:.2f}") for k in ("open", "high", "low", "close")],
            Quantity.from_int(int(r["volume"])),
            ts_event=int(r["timestamp"] * 1e9),
            ts_init=int(r["timestamp"] * 1e9),
        )
        for r in rows
    ]
    capital = Decimal("100000")
    envelope = artifact["nautilus"]["risk_envelope"]
    cap = Decimal(envelope["max_order_value"])
    loss_limit = Decimal(envelope["max_daily_loss"])
    if envelope.get("max_gross_exposure") is not None:
        cap = min(cap, Decimal(envelope["max_gross_exposure"]))

    class Replay(Strategy):
        def __init__(self):
            super().__init__(StrategyConfig(strategy_id=StrategyId("StudioOHLC-001")))
            self.window = []
            self.cash = capital
            self.quantity = Decimal(0)
            self.curve = []
            self.fills = []
            self.pending = False
            self.days = {}
            self.blocked = 0
            self.signal_ts = None

        def on_start(self):
            self.subscribe_bars(bar_type)

        def on_order_filled(self, event):
            qty, price = Decimal(str(event.last_qty)), Decimal(str(event.last_px))
            buy = event.order_side == OrderSide.BUY
            self.quantity += qty if buy else -qty
            self.cash += -qty * price if buy else qty * price
            self.pending = False
            self.fills.append(
                {
                    "event": str(event.ts_event),
                    "side": "BUY" if buy else "SELL",
                    "qty": str(qty),
                    "price": str(price),
                    "order_id": str(event.client_order_id),
                    "fee": "0.00",
                    "signal_ts": self.signal_ts,
                }
            )

        def on_order_rejected(self, event):
            self.pending = False
            self.blocked += 1

        def on_bar(self, bar):
            # Signals use only prior completed bars. The engine may fill at
            # this bar's close; current OHLC never enters the signal window.
            price = Decimal(str(bar.close))
            equity = self.cash + self.quantity * price
            day = bar.ts_event // 86_400_000_000_000
            self.days.setdefault(day, Decimal(self.curve[-1]["equity"]) if self.curve else capital)
            self.curve.append(
                {"ts": bar.ts_event / 1e9, "event": str(bar.ts_event), "equity": f"{equity:.2f}"}
            )
            previous = self.window[:]
            self.window.append(
                EvalBar(
                    *[float(getattr(bar, k)) for k in ("open", "high", "low", "close", "volume")]
                )
            )
            if len(previous) < warmup or self.pending:
                return
            signal = evaluate(spec, previous)
            self.signal_ts = rows[len(previous) - 1]["timestamp"]
            if self.quantity > 0 and signal.exit:
                side, qty = OrderSide.SELL, int(self.quantity)
            elif self.quantity == 0 and signal.entry:
                if equity - self.days[day] <= -loss_limit:
                    self.blocked += 1
                    return
                # Limit price enforces the dollar cap even through price gaps.
                prior_close = Decimal(str(previous[-1].close))
                side, qty = OrderSide.BUY, int(min(cap, self.cash) / prior_close)
                qty = min(qty, 1)
            else:
                return
            if qty <= 0:
                self.blocked += 1
                return
            self.pending = True
            if side == OrderSide.BUY:
                order = self.order_factory.limit(
                    instrument_id=instrument.id,
                    order_side=side,
                    quantity=Quantity.from_int(qty),
                    price=Price.from_str(f"{min(cap, self.cash):.2f}"),
                )
            else:
                order = self.order_factory.market(
                    instrument_id=instrument.id, order_side=side, quantity=Quantity.from_int(qty)
                )
            self.submit_order(order)

    engine = BacktestEngine(config=BacktestEngineConfig())
    strategy = Replay()
    try:
        engine.add_venue(
            venue=Venue("NYSE"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=usd,
            starting_balances=[Money.from_str("100000 USD")],
            fee_model=FixedFeeModel(Money.from_str("0 USD")),
        )
        engine.add_instrument(instrument)
        engine.add_strategy(strategy)
        engine.add_data(bars)
        engine.run()
        if engine.iteration != len(rows):
            raise ValueError("engine did not consume every selected snapshot bar")
        ending = strategy.cash + strategy.quantity * Decimal(str(bars[-1].close))
        peak, drawdown = capital, Decimal(0)
        for point in strategy.curve:
            value = Decimal(point["equity"])
            peak = max(peak, value)
            drawdown = max(drawdown, peak - value)
        return {
            "executor": "NautilusTrader BacktestEngine 2.0.0rc6",
            "engine": {"iterations": engine.iteration, "strategy_id": "StudioOHLC-001"},
            "implementation": artifact["implementation"],
            "params": {
                "execution": "prior-bar signals; close fills; cap-limited buy; one share",
                "fees": "zero assumed",
                "open_position": str(strategy.quantity),
            },
            "risk_envelope": envelope,
            "metrics": {
                "intervals": len(rows),
                "filled": len(strategy.fills),
                "blocked": strategy.blocked,
                "starting_equity": str(capital),
                "ending_equity": f"{ending:.2f}",
                "pnl": f"{ending - capital:.2f}",
                "fees": "0.00",
                "max_drawdown": f"{drawdown:.2f}",
            },
            "equity_curve": strategy.curve,
            "trades": strategy.fills,
        }
    finally:
        engine.dispose()
