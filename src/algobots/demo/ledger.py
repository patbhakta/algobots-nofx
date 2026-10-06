"""Paper ledger: feed rows -> strategy decisions -> risk gate -> paper fills.

Feed rows come from the Laya forward observer (``observations.jsonl``): one
row per settled KXBTC15M interval with Laya's calibrated P(up) and the Jev
arm's choice, both computed from PRIOR intervals only, then scored at
settlement. The PoC captures no order book, so every fill is at the assumed
50c mid and pays the Kalshi taker fee; the page says so.

Everything here is a pure function of (rows, kill-switch state), so the
ledger is deterministic and recomputed on every request.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path

from algobots.risk import RiskEnvelope

CENT = Decimal("0.01")
FILL_PRICE = Decimal("0.50")  # PoC records no quotes: assumed mid
KALSHI_FEE_RATE = Decimal("0.07")  # taker fee = ceil(0.07 * C * P * (1-P)) to the cent
MIN_STAKE = Decimal("5")
SLEEVE = Decimal("100")  # starting paper capital per strategy
ENVELOPE = RiskEnvelope(max_order_value=Decimal("15"), max_daily_loss=Decimal("40"))
LAYA_MIN_EDGE = 0.02  # |P(up) - 0.5| below this -> abstain

STRATEGIES = {
    "laya": "Laya System One",
    "jev": "Jev zero-shot",
    "coin": "Coin-flip control",
}


@dataclass(frozen=True)
class Row:
    event: str
    strike: float
    outcome: int  # 1 = BTC closed above strike
    ts: float
    p: float
    conf: float
    jev_p: float | None
    jev_conf: float | None
    jev_choice: str | None


@dataclass
class Decision:
    strategy: str
    event: str
    ts: float
    side: str | None  # YES (up) / NO (down) / None = abstain
    status: str  # FILLED / ABSTAIN / BLOCKED
    reason: str
    requested: Decimal = Decimal(0)
    stake: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    pnl: Decimal = Decimal(0)
    won: bool | None = None
    clamped: bool = False


@dataclass
class StrategyBook:
    key: str
    name: str
    decisions: list[Decision] = field(default_factory=list)
    curve: list[tuple[float, Decimal]] = field(default_factory=list)

    @property
    def fills(self) -> list[Decision]:
        return [d for d in self.decisions if d.status == "FILLED"]

    @property
    def pnl(self) -> Decimal:
        return sum((d.pnl for d in self.fills), Decimal(0))

    @property
    def fees(self) -> Decimal:
        return sum((d.fee for d in self.fills), Decimal(0))

    @property
    def wins(self) -> int:
        return sum(1 for d in self.fills if d.won)

    @property
    def equity(self) -> Decimal:
        return SLEEVE + self.pnl

    @property
    def max_drawdown(self) -> Decimal:
        peak, worst = SLEEVE, Decimal(0)
        for _, eq in self.curve:
            peak = max(peak, eq)
            worst = min(worst, eq - peak)
        return worst


@dataclass
class Ledger:
    rows: list[Row]
    books: dict[str, StrategyBook]
    kill: dict
    clamp_events: list[Decision]

    @property
    def last_ts(self) -> float | None:
        return self.rows[-1].ts if self.rows else None


def load_rows(path: Path, since_ts: float = 0.0) -> list[Row]:
    """Parse the observer jsonl from ``since_ts``; skip malformed lines; order by time."""
    rows: list[Row] = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
            rows.append(
                Row(
                    event=r["event"],
                    strike=float(r["strike"]),
                    outcome=int(r["outcome"]),
                    ts=float(r["ts"]),
                    p=float(r["p"]),
                    conf=float(r.get("conf") or 0),
                    jev_p=r.get("jev_p"),
                    jev_conf=r.get("jev_conf"),
                    jev_choice=r.get("jev_choice"),
                )
            )
        except (ValueError, KeyError, TypeError):
            continue
    rows = [r for r in rows if r.ts >= since_ts]
    rows.sort(key=lambda r: r.ts)
    return rows


def fee_for(stake: Decimal, price: Decimal = FILL_PRICE) -> Decimal:
    contracts = stake / price
    raw = KALSHI_FEE_RATE * contracts * price * (1 - price)
    return raw.quantize(CENT, rounding=ROUND_CEILING)


def _money(x: float | Decimal) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def _intent(key: str, row: Row) -> tuple[str | None, Decimal, str]:
    """Strategy signal: (side, requested stake, human reason)."""
    if key == "laya":
        edge = row.p - 0.5
        if abs(edge) < LAYA_MIN_EDGE:
            return (
                None,
                Decimal(0),
                (f"P(up) {row.p:.3f} is within ±{LAYA_MIN_EDGE:.2f} of 50% — no edge, abstain"),
            )
        side = "YES" if edge > 0 else "NO"
        req = _money(MIN_STAKE + Decimal(10) * Decimal(str(abs(edge) / 0.05)))
        return side, req, (f"P(up) {row.p:.3f} vs 0.50 mid → edge {edge * 100:+.1f}pp → {side}")
    if key == "jev":
        if row.jev_choice not in ("up", "down"):
            return None, Decimal(0), "Jev arm returned no choice for this interval"
        side = "YES" if row.jev_choice == "up" else "NO"
        conf = float(row.jev_conf or 0)
        req = _money(MIN_STAKE + Decimal(10) * Decimal(str(min(1.0, conf))))
        return (
            side,
            req,
            f"Jev chose {row.jev_choice} (P(up) {row.jev_p}, conf {conf:.2f}) → {side}",
        )
    # coin: deterministic per event so every replay agrees
    heads = hashlib.sha256(row.event.encode()).digest()[0] & 1
    side = "YES" if heads else "NO"
    return side, Decimal(10), f"sha256(event) coin → {'heads' if heads else 'tails'} → {side}"


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def build(rows: Iterable[Row], kill: dict | None = None) -> Ledger:
    """Replay rows through every strategy behind the risk envelope + kill switch."""
    rows = list(rows)
    kill = kill or {"engaged": False}
    books = {k: StrategyBook(k, n) for k, n in STRATEGIES.items()}
    clamps: list[Decision] = []
    for key, book in books.items():
        equity = SLEEVE
        daily: dict[str, Decimal] = {}
        for row in rows:
            side, req, why = _intent(key, row)
            d = Decision(key, row.event, row.ts, side, "ABSTAIN", why, requested=req)
            day = _day(row.ts)
            if side is not None:
                if kill.get("engaged") and row.ts >= float(kill.get("since_ts") or 0):
                    d.status, d.reason = "BLOCKED", f"{why}; kill switch engaged — entry blocked"
                elif ENVELOPE.check_daily_loss(daily.get(day, Decimal(0))).tripped:
                    d.status = "BLOCKED"
                    d.reason = (
                        f"{why}; daily-loss envelope (−{ENVELOPE.max_daily_loss} USD) exhausted"
                    )
                elif equity < MIN_STAKE + fee_for(MIN_STAKE):
                    d.status = "BLOCKED"
                    d.reason = f"{why}; sleeve equity {equity} USD below minimum stake + fee"
                else:
                    check = ENVELOPE.clamp_order_value(req)
                    # stake + fee never exceeds what the sleeve holds
                    affordable = (equity - fee_for(equity)).quantize(CENT)
                    d.stake, d.clamped = min(check.approved, affordable), check.fired
                    d.fee = fee_for(d.stake)
                    d.won = (side == "YES") == (row.outcome == 1)
                    # binary at 50c: win pays stake (contracts * $1 - cost), loss forfeits it
                    d.pnl = (d.stake if d.won else -d.stake) - d.fee
                    d.status = "FILLED"
                    if d.clamped:
                        d.reason += f"; size clamped {req} → {d.stake} USD (max order value)"
                        clamps.append(d)
                    daily[day] = daily.get(day, Decimal(0)) + d.pnl
                    equity += d.pnl
            book.decisions.append(d)
            book.curve.append((row.ts, equity))
    return Ledger(rows=rows, books=books, kill=kill, clamp_events=clamps)


def brier(rows: list[Row]) -> float | None:
    if not rows:
        return None
    return sum((r.p - r.outcome) ** 2 for r in rows) / len(rows)


def hit_rate(book: StrategyBook) -> float | None:
    fills = book.fills
    return book.wins / len(fills) if fills else None


def sharpe_like(book: StrategyBook) -> float | None:
    """Mean/stdev of per-fill P&L (not annualized) — a stability read, not a claim."""
    xs = [float(d.pnl) for d in book.fills]
    if len(xs) < 2:
        return None
    mu = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))
    return mu / sd if sd else None
