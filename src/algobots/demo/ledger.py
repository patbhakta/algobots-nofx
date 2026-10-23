"""Paper ledger: feed rows -> strategy decisions -> risk gate -> paper fills.

Feed rows come from the Laya forward observer (``observations.jsonl``): one
row per settled KXBTC15M interval with Laya's calibrated P(up) and the Jev
arm's choice, both computed from PRIOR intervals only, then scored at
settlement. The PoC captures no order book, so every fill is at the assumed
50c mid and pays the Kalshi taker fee; the page says so.

Execution (ALG-3289): ``build`` decides and risk-gates every entry, then
hands each approved entry to an executor. The dashboard passes
``algobots.engine.sleeve.NautilusSleeve``: the order fills on a Nautilus
simulated venue, which charges the fee, settles the contract and holds the
sleeve's cash, and the qty, stake, fee, P&L and equity recorded here are
read back from that engine. Without an executor (unit tests; Nautilus not
installed) the in-process reference model below computes them instead, and
``Ledger.executor`` names which one produced the numbers.

Everything here is a pure function of (rows, kill-switch state), so the
ledger is deterministic and recomputed whenever its inputs change.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Protocol

from algobots.demo import gate
from algobots.risk import RiskEnvelope

CENT = Decimal("0.01")
FILL_PRICE = Decimal("0.50")  # fallback fill price when a row captured no book
KALSHI_FEE_RATE = Decimal("0.07")  # taker fee = ceil(0.07 * C * P * (1-P)) to the cent
MIN_STAKE = Decimal("5")
SLEEVE = Decimal("100")  # starting paper capital per strategy
ENVELOPE = RiskEnvelope(max_order_value=Decimal("15"), max_daily_loss=Decimal("40"))
LAYA_MIN_EDGE = 0.02  # |P(up) - 0.5| below this -> abstain
REFERENCE = "reference model (assumed-mid arithmetic, no engine)"

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
    mkt_mid: float | None = None  # Kalshi YES mid at decision time (None = no book)
    mkt_yes_bid: float | None = None  # Kalshi YES bid at decision time
    mkt_yes_ask: float | None = None  # Kalshi YES ask at decision time


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
    qty: int = 0  # contracts filled
    price: Decimal = Decimal(0)  # average fill price
    order_id: str | None = None  # executor's client order ID
    px_source: str = ""  # where d.price came from: book ask, or assumed 50c mid


@dataclass
class StrategyBook:
    key: str
    name: str
    decisions: list[Decision] = field(default_factory=list)
    curve: list[tuple[float, Decimal]] = field(default_factory=list)
    refills: list[tuple[float, Decimal]] = field(default_factory=list)  # (ts, USD added)

    @property
    def allocated(self) -> Decimal:
        return SLEEVE + sum((amt for _, amt in self.refills), Decimal(0))

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
        return self.allocated + self.pnl

    @property
    def exhausted(self) -> bool:
        return self.equity < MIN_STAKE + fee_for(MIN_STAKE)

    @property
    def max_drawdown(self) -> Decimal:
        # drawdown on cumulative P&L, so a refill never looks like a recovery
        peak, worst = Decimal(0), Decimal(0)
        for _, pnl in self.pnl_curve:
            peak = max(peak, pnl)
            worst = min(worst, pnl - peak)
        return worst

    @property
    def pnl_curve(self) -> list[tuple[float, Decimal]]:
        out, added, i = [], Decimal(0), 0
        for ts, eq in self.curve:
            while i < len(self.refills) and self.refills[i][0] <= ts:
                added += self.refills[i][1]
                i += 1
            out.append((ts, eq - SLEEVE - added))
        return out


@dataclass
class Ledger:
    rows: list[Row]
    books: dict[str, StrategyBook]
    kill: dict
    clamp_events: list[Decision]
    refill_ts: list[float] = field(default_factory=list)
    executor: str = REFERENCE

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
                    mkt_mid=(
                        float(r["mkt_mid"])
                        if isinstance(r.get("mkt_mid"), int | float)
                        else None
                    ),
                    mkt_yes_bid=(
                        float(r["mkt_yes_bid"])
                        if isinstance(r.get("mkt_yes_bid"), int | float)
                        else None
                    ),
                    mkt_yes_ask=(
                        float(r["mkt_yes_ask"])
                        if isinstance(r.get("mkt_yes_ask"), int | float)
                        else None
                    ),
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


def interval_ts(row: Row) -> float:
    """When the interval's decision was due, from the ticker (``KXBTC15M-26SEP181245``).

    The observer backfills missed intervals in bursts, so ``row.ts`` (write time)
    can put dozens of decisions in one minute; the rate breakers count decisions
    at their scheduled time instead. Falls back to ``row.ts`` for odd tickers.
    """
    try:
        return (
            datetime.strptime(row.event.split("-")[1], "%y%b%d%H%M").replace(tzinfo=UTC).timestamp()
        )
    except (IndexError, ValueError):
        return row.ts


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


class Sleeve(Protocol):
    """Executes one sleeve's entries; ``algobots.engine.sleeve.NautilusSleeve`` in production."""

    @property
    def equity(self) -> Decimal: ...

    def top_up(self, amount: Decimal) -> None: ...

    def execute(  # noqa: ANN201
        self, event: str, side: str, ts: float, won: bool, qty: int, px: Decimal = FILL_PRICE
    ): ...

    def close(self) -> None: ...


def contracts(stake: Decimal, price: Decimal = FILL_PRICE) -> int:
    """Whole contracts a stake buys at ``price`` (Kalshi trades whole contracts)."""
    return math.floor(stake / price)


PX_ASSUMED = "assumed_mid"


def exec_px(row: Row, side: str) -> tuple[Decimal, str]:
    """Executable price for ``side``: cross the recorded spread, never the mid.

    YES pays the ask; NO pays 1 - bid (the NO ask). GATE-VERDICT-v2: a
    participant cannot monetize the mid against itself. Rows that captured
    no book fill at the assumed 50c mid, labelled ``PX_ASSUMED``.
    """
    bid, ask = row.mkt_yes_bid, row.mkt_yes_ask
    if side == "YES" and ask is not None and 0.0 < ask < 1.0:
        return _money(ask), "kalshi_yes_ask"
    if side == "NO" and bid is not None and 0.0 < bid < 1.0:
        return _money(1 - bid), "kalshi_no_ask"
    return FILL_PRICE, PX_ASSUMED


def build(
    rows: Iterable[Row],
    kill: dict | None = None,
    refills: Iterable[float] = (),
    executor: Callable[[str, Decimal], Sleeve] | None = None,
    executor_name: str = REFERENCE,
) -> Ledger:
    """Replay rows through every strategy behind the risk envelope + kill switch.

    ``refills`` are timestamps at which every sleeve is topped back up to
    SLEEVE. The top-up is recorded as added capital, never as P&L, so net
    P&L stays cumulative and honest across refills.

    ``executor(account, capital)`` opens one sleeve per account. Every
    approved entry executes on it, and the decision's qty, price, stake, fee
    and P&L, and the equity the risk gate sees next, are read back from it.
    """
    rows = list(rows)
    refill_ts = sorted(refills)
    kill = kill or {"engaged": False}
    books = {k: StrategyBook(k, n) for k, n in STRATEGIES.items()}
    clamps: list[Decision] = []
    risk = gate.risk_gate(ENVELOPE)  # one gate per replay: breakers see the whole fleet
    for key, book in books.items():
        sleeve = executor(key, SLEEVE) if executor else None
        try:
            _replay(key, book, rows, kill, refill_ts, clamps, sleeve, risk)
        finally:
            if sleeve is not None:
                sleeve.close()
    name = executor_name if executor else REFERENCE
    return Ledger(rows, books, kill, clamps, refill_ts, executor=name)


def _replay(
    key: str,
    book: StrategyBook,
    rows: list[Row],
    kill: dict,
    refill_ts: list[float],
    clamps: list[Decision],
    sleeve: Sleeve | None,
    risk: gate.RiskGate,
) -> None:
    equity = SLEEVE
    daily: dict[str, Decimal] = {}
    pending = list(refill_ts)
    for row in rows:
        while pending and pending[0] <= row.ts:
            top_up = SLEEVE - equity
            if top_up > 0:
                book.refills.append((pending[0], top_up))
                if sleeve is not None:
                    sleeve.top_up(top_up)
                equity = SLEEVE
            pending.pop(0)
        side, req, why = _intent(key, row)
        d = Decision(key, row.event, row.ts, side, "ABSTAIN", why, requested=req)
        day = _day(row.ts)
        if side is not None:
            g = gate.pre_trade(
                gate.GateRequest(
                    account=key,
                    path="strategy",
                    value=req,
                    equity=equity,
                    floor=MIN_STAKE + fee_for(MIN_STAKE),  # == StrategyBook.exhausted
                    daily_pnl=daily.get(day, Decimal(0)),
                    kill_engaged=bool(kill.get("engaged"))
                    and row.ts >= float(kill.get("since_ts") or 0),
                    now=interval_ts(row),
                    ticker=row.event,
                    fee=fee_for,
                ),
                risk,
            )
            if not g.allowed:
                d.status, d.reason = "BLOCKED", f"{why}; {g.reason}"
            else:
                d.stake, d.clamped = g.approved, g.clamped
                d.won = (side == "YES") == (row.outcome == 1)
                px, px_source = exec_px(row, side)
                if sleeve is not None:
                    x = sleeve.execute(
                        row.event, side, row.ts, d.won, contracts(d.stake, px), px
                    )
                    d.qty, d.price, d.order_id = x.qty, x.price, x.client_order_id
                    d.stake, d.fee, d.pnl = x.cost, x.fee, x.pnl
                else:
                    d.qty = contracts(d.stake, px)
                    d.price = px
                    d.stake = (Decimal(d.qty) * px).quantize(
                        CENT, rounding=ROUND_HALF_UP
                    )
                    d.fee = fee_for(d.stake, px)
                    # binary at px: win pays qty * (1 - px), loss forfeits the cost
                    d.pnl = (
                        Decimal(d.qty) * (Decimal(1) - px) if d.won else -d.stake
                    ) - d.fee
                d.px_source = px_source
                d.status = "FILLED"
                if d.clamped:
                    d.reason += f"; {g.reason}"
                    clamps.append(d)
                daily[day] = daily.get(day, Decimal(0)) + d.pnl
                equity = sleeve.equity if sleeve is not None else equity + d.pnl
        book.decisions.append(d)
        book.curve.append((row.ts, equity))


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
