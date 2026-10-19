"""Public Binance bars for paper-only Nautilus research.

Instrument metadata is loaded through Nautilus' rc6 Binance adapter.  Closed
klines use Binance's unauthenticated REST endpoint and are then replayed as
native ``Bar`` objects by ``BacktestEngine``.  No credentials or order client
are involved.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

# Binance's official market-data-only domain is keyless and remains available
# in regions where the trading API correctly returns HTTP 451.
BINANCE_DATA_URL = "https://data-api.binance.vision"
BINANCE_KLINES_URL = f"{BINANCE_DATA_URL}/api/v3/klines"


@dataclass(frozen=True)
class PublicBar:
    open_time_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    close_time_ms: int


def parse_klines(payload: Any) -> list[PublicBar]:
    """Validate Binance's compact kline response and discard an open candle."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("Binance returned no klines")
    bars: list[PublicBar] = []
    for index, row in enumerate(payload):
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError(f"Binance kline {index} is malformed")
        bars.append(
            PublicBar(
                open_time_ms=int(row[0]),
                open=str(row[1]),
                high=str(row[2]),
                low=str(row[3]),
                close=str(row[4]),
                volume=str(row[5]),
                close_time_ms=int(row[6]),
            )
        )
    return bars


def fetch_public_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    limit: int = 100,
    *,
    opener: Callable[..., Any] = urlopen,
) -> list[PublicBar]:
    if not 2 <= limit <= 1000:
        raise ValueError("limit must be between 2 and 1000")
    query = urlencode({"symbol": symbol.upper(), "interval": interval, "limit": limit})
    with opener(f"{BINANCE_KLINES_URL}?{query}", timeout=15) as response:
        return parse_klines(json.load(response))


async def _instrument(instrument_id: str):
    from nautilus_trader.adapters.binance import (
        BinanceDataClientConfig,
        BinanceEnvironment,
        BinanceInstrumentProviderConfig,
        BinanceProductType,
        load_binance_instruments,
    )

    config = BinanceDataClientConfig(
        product_type=BinanceProductType.SPOT,
        environment=BinanceEnvironment.LIVE,
        base_url_http=BINANCE_DATA_URL,
        instrument_provider=BinanceInstrumentProviderConfig(
            load_all=False,
            load_ids=[instrument_id],
        ),
    )
    instruments = await load_binance_instruments(config)
    if len(instruments) != 1:
        raise RuntimeError(f"expected one Binance instrument, received {len(instruments)}")
    return instruments[0], config


def _load_instrument(instrument_id: str):
    """Bridge the async adapter loader from scripts and marimo's running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_instrument(instrument_id))
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, _instrument(instrument_id)).result()


def run_backtest(bars: list[PublicBar], instrument_id: str = "BTCUSDT.BINANCE") -> dict[str, Any]:
    """Load public instrument metadata and replay closed bars through rc6."""
    from nautilus_trader.backtest import BacktestEngine, BacktestEngineConfig
    from nautilus_trader.execution import FixedFeeModel
    from nautilus_trader.model import AccountType, Bar, BarType, Money, OmsType, TraderId

    instrument, config = _load_instrument(instrument_id)
    bar_type = BarType.from_str(f"{instrument_id}-1-MINUTE-LAST-EXTERNAL")
    native = [
        Bar(
            bar_type,
            instrument.make_price(float(row.open)),
            instrument.make_price(float(row.high)),
            instrument.make_price(float(row.low)),
            instrument.make_price(float(row.close)),
            instrument.make_qty(float(row.volume)),
            row.close_time_ms * 1_000_000,
            row.close_time_ms * 1_000_000,
        )
        for row in bars[:-1]  # The last REST candle may still be forming.
    ]
    engine = BacktestEngine(
        BacktestEngineConfig(
            trader_id=TraderId.from_str("BINANCE-RESEARCH-001"),
            bypass_logging=True,
        )
    )
    engine.add_venue(
        instrument.id.venue,
        OmsType.NETTING,
        AccountType.CASH,
        [Money.from_str(f"100000 {instrument.quote_currency.code}")],
        fee_model=FixedFeeModel(Money.from_str(f"0 {instrument.quote_currency.code}")),
    )
    engine.add_instrument(instrument)
    engine.add_data(native)
    engine.run()
    result = {
        "adapter_config": type(config).__name__,
        "engine": type(engine).__name__,
        "instrument": str(instrument.id),
        "bars_fetched": len(bars),
        "bars_replayed": len(native),
        "first": asdict(bars[0]),
        "last_closed": asdict(bars[-2]),
        "no_api_key": True,
    }
    engine.dispose()
    return result


def fetch_and_run(symbol: str = "BTCUSDT", limit: int = 100) -> dict[str, Any]:
    return run_backtest(fetch_public_klines(symbol=symbol, limit=limit), f"{symbol}.BINANCE")
