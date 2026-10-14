"""Cache-first Massive (Polygon) aggregate data for research backtests.

Massive is a research data source only. Broker data remains authoritative for
orders and fills. API responses are cached on FunnyTree so notebooks do not
re-fetch identical history and consume the plan's rate limit.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

MASSIVE_BASE_URL = "https://api.massive.com"
DEFAULT_CACHE_ROOT = Path("/mnt/funnytree/market-data/massive")
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
_TIMESPANS = {"second", "minute", "hour", "day", "week", "month", "quarter", "year"}


def _default_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS origin
        return json.load(response)


def _cache_file(
    root: Path, ticker: str, start: date, end: date, multiplier: int, timespan: str
) -> Path:
    return root / ticker / timespan / f"{multiplier}-{start.isoformat()}-{end.isoformat()}.json"


def fetch_aggregates(
    ticker: str,
    start: date,
    end: date,
    *,
    multiplier: int = 1,
    timespan: str = "day",
    cache_root: Path | str | None = None,
    api_key: str | None = None,
    transport: Callable[[str, dict[str, str]], dict[str, Any]] = _default_transport,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return normalized OHLCV aggregates, reading/writing FunnyTree cache.

    ``api_key`` is accepted for tests and controlled callers. Normal notebook
    use reads ``MASSIVE_API_KEY`` from the process environment only.
    """
    ticker = ticker.strip().upper()
    if not _SYMBOL.fullmatch(ticker):
        raise ValueError("ticker must be a US-equity symbol")
    if start > end:
        raise ValueError("start must be on or before end")
    if multiplier < 1 or multiplier > 50_000:
        raise ValueError("multiplier must be between 1 and 50000")
    if timespan not in _TIMESPANS:
        raise ValueError(f"unsupported timespan: {timespan}")

    root = Path(cache_root or os.getenv("MASSIVE_CACHE_ROOT", DEFAULT_CACHE_ROOT))
    target = _cache_file(root, ticker, start, end, multiplier, timespan)
    if target.is_file() and not force_refresh:
        result = json.loads(target.read_text())
        result["cache"] = "hit"
        return result

    key = api_key or os.getenv("MASSIVE_API_KEY")
    if not key:
        raise RuntimeError("MASSIVE_API_KEY is required on a cache miss")
    path = (
        f"/v2/aggs/ticker/{quote(ticker, safe='')}/range/{multiplier}/{timespan}/"
        f"{start.isoformat()}/{end.isoformat()}"
    )
    query = urlencode({"adjusted": "true", "sort": "asc", "limit": 50_000})
    payload = transport(f"{MASSIVE_BASE_URL}{path}?{query}", {"Authorization": f"Bearer {key}"})
    if payload.get("status") not in {"OK", "DELAYED"}:
        detail = payload.get("error", payload.get("status"))
        raise RuntimeError(f"Massive aggregates request failed: {detail}")

    bars = [
        {
            "ts_event_ms": int(row["t"]),
            "open": float(row["o"]),
            "high": float(row["h"]),
            "low": float(row["l"]),
            "close": float(row["c"]),
            "volume": float(row["v"]),
            "transactions": int(row.get("n", 0)),
            "vwap": float(row["vw"]) if row.get("vw") is not None else None,
        }
        for row in payload.get("results", [])
    ]
    result = {
        "provider": "Massive",
        "purpose": "research-only; broker prices are fill truth",
        "ticker": ticker,
        "timespan": timespan,
        "multiplier": multiplier,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "bars": bars,
        "cache": "miss",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=target.parent, delete=False) as temporary:
        json.dump(result, temporary, separators=(",", ":"))
        temporary.flush()
        temporary_path = Path(temporary.name)
    temporary_path.replace(target)
    return result
