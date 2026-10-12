"""A05 demo: two asset classes in one watchlist with market status, data
timestamps and precision; writes artifacts/A05/demo-and-limitations.md.

    python tests/packets/A05/demo.py
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from algobots.instruments import default_registry, round_price, round_quantity
from algobots.marketdata import ReplayFeed, load_fx_book, load_recording, watchlist_status

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A05" / "demo-and-limitations.md"

WATCHLIST = (
    "XNAS:equity:AAPL",
    "XNYS:etf:SPY",
    "COINBASE:spot-crypto:BTC-USD",
    "KRAKEN:spot-crypto:BTC-USD",
    "BYBIT:perpetual-swap:BTC-PERP",
)
SESSION_AS_OF = datetime(2026, 10, 31, 15, 0, 30, tzinfo=UTC)  # Saturday
OPEN_AS_OF = datetime(2026, 10, 30, 14, 5, 30, tzinfo=UTC)  # Friday session


def _row_markdown(row: dict) -> str:
    return (
        f"| {row['instrument_id']} | {row['product']} | "
        f"{'OPEN' if row['market_open'] else 'CLOSED'} ({row['market_reason']}) | "
        f"{row['last_event_time'] or '—'} | {row['last_available_time'] or '—'} | "
        f"{row['source'] or '—'}#{row['sequence'] if row['sequence'] is not None else '—'} | "
        f"{row['age_seconds'] if row['age_seconds'] is not None else '—'}s | "
        f"{row['price_precision']} / {row['quantity_precision']} | "
        f"{row['quote_currency']} | {'fresh' if row['fresh'] else 'stale'} | "
        f"{'yes' if row['eligible'] else 'no'} |"
    )


def main() -> int:
    registry = default_registry()
    feed = ReplayFeed(load_recording())
    header = (
        "| instrument | product | market status | last event (UTC) | available (UTC) | "
        "source#seq | age | price/qty decimals | ccy | data | eligible |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|"
    )

    saturday_rows = watchlist_status(WATCHLIST, feed, SESSION_AS_OF)
    friday_rows = watchlist_status(("XNAS:equity:AAPL", "COINBASE:spot-crypto:BTC-USD"), feed, OPEN_AS_OF)

    # Rounding showcase (acceptance case 2 shape) on two precision regimes.
    aapl = registry.get("XNAS:equity:AAPL")
    btc = registry.get("COINBASE:spot-crypto:BTC-USD")
    perp = registry.get("BYBIT:perpetual-swap:BTC-PERP")
    roundings = [
        ("AAPL price 227.755 -> tick 0.01 (nearest)", round_price(aapl, Decimal("227.755"))),
        ("AAPL quantity 10.5 shares -> lot 1 (down)", round_quantity(aapl, Decimal("10.5"))),
        ("BTC price 61000.14 -> tick 0.01 (nearest)", round_price(btc, Decimal("61000.14"))),
        ("BTC quantity 0.123456789 BTC -> lot 1e-8 (down)", round_quantity(btc, Decimal("0.123456789"))),
        ("PERP price 61052.15 -> tick 0.1 (nearest)", round_price(perp, Decimal("61052.15"))),
    ]

    fx = load_fx_book()
    fx_line = fx.rate("EUR", "USD", datetime(2026, 10, 30, 12, 0, tzinfo=UTC))

    lines = [
        "# A05 demo and limitations",
        "",
        "Instrument registry, recorded replay, and mixed-asset-class watchlist from the",
        "A05 branch (`feat/alg-3101-a05-instrument-marketdata`). All data is deterministic",
        "recorded fixtures — no live feeds were touched.",
        "",
        "## Demo — two asset classes in one watchlist",
        "",
        f"As-of **Saturday 2026-10-31 15:00:30 UTC** (weekend): the equity and ETF are",
        "closed with explicit weekend reasons, spot crypto and the perpetual are open 24x7,",
        "and each row carries its data timestamps, source/sequence, age and configured precision.",
        "",
        header,
        *[_row_markdown(row) for row in saturday_rows],
        "",
        f"As-of **Friday 2026-10-30 14:05:30 UTC** (regular equity session): both classes",
        "open and fresh on their latest prints.",
        "",
        header,
        *[_row_markdown(row) for row in friday_rows],
        "",
        "## Precision and explicit residuals (tick/lot boundaries)",
        "",
        "| rounding | value | residual | increments |",
        "|---|---|---|---|",
        *[
            f"| {label} | {r.value} | {r.residual} | {r.increments} |"
            for label, r in roundings
        ],
        "",
        "## FX conversion snapshots (reporting)",
        "",
        f"EUR/USD as-of 2026-10-30 12:00 UTC = {fx_line} (point-in-time). Unavailable pairs",
        "raise `FxUnavailableError` — they are never reinterpreted as 1:1.",
        "",
        "## Limitations",
        "",
        "- **Calendars**: US equity sessions model Mon-Fri 09:30-16:00 America/New_York with",
        "  DST via zoneinfo; **exchange holidays are not modeled** (a holiday weekday shows",
        "  as open until a holiday calendar lands).",
        "- **Perpetual swap is identity-only**: distinct executable ID, no execution support",
        "  (A05 excludes options/futures execution; no universal-symbology claims).",
        "- **Recorded fixtures only**: 5 instruments, 19 snapshots, 3 FX quotes; adapters are",
        "  source-agnostic JSONL replays — Laya/Jev dropped per ALG-3309; no venue API is called.",
        "- **Corrections amend quotes, not bars**: a later-published corrected price updates",
        "  the point-in-time quote; bar history keeps what the tape printed at the time.",
        "- **Seams left for their owners**: A06 `engine/workers/paper.py` ad-hoc Nautilus",
        "  instruments, `engine/workers/fixture.py` synthetic quote stream, and `sleeve.py`",
        "  Kalshi identities remain as-is; re-homing them onto this registry is out of scope.",
        "- **External-environment cases are BLOCKED** and never claimed: this evidence is",
        "  development/synthetic-paper only.",
        "",
        "## Router mount (proposal through the api owner)",
        "",
        "`/instruments` and `/market-data/status` are implemented in",
        "`algobots.marketdata.routes` and mounted in `api/main.py` as a one-line-per-router",
        "proposal per the A03/A04 mount precedent (see the A05 scope guard).",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(saturday_rows)} Saturday rows, {len(friday_rows)} Friday rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
