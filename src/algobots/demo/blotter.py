"""Terminal views over the paper ledger: account context, positions, orders, risk.

Pure functions of (ledger, now, account) shared by the /demo panes and the
JSON endpoints, so the page and the API can never disagree.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from algobots.demo import ledger as L
from algobots.demo import studio as S

LIVE = {d.account: d for d in S.LIVE_DEPLOYMENTS}
EQUITY = tuple(k for k, a in S.ACCOUNTS.items() if a.venue == "equities")  # template accounts
ORDER = {k: i for i, k in enumerate(S.ACCOUNTS)}

ALL = "all"
STATUSES = ("filled", "blocked", "abstain")
INSTRUMENT = "KXBTC15M"


def account_key(raw: str | None) -> str:
    """Normalise ``?account=``; anything unknown falls back to the aggregate."""
    key = (raw or ALL).strip().lower()
    return key if key in L.STRATEGIES or key in EQUITY else ALL


def status_key(raw: str | None) -> str | None:
    key = (raw or "").strip().lower()
    return key if key in STATUSES else None


def books(lg: L.Ledger, account: str) -> list[L.StrategyBook]:
    """Kalshi ledger books in context; an equities template account has none."""
    if account in EQUITY:
        return []
    return list(lg.books.values()) if account == ALL else [lg.books[account]]


def today(now: float) -> str:
    return datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")


def day_pnl(b: L.StrategyBook, day: str) -> Decimal:
    return sum((d.pnl for d in b.fills if L._day(d.ts) == day), Decimal(0))


def halt(lg: L.Ledger, b: L.StrategyBook, day: str) -> str | None:
    """Why new entries are blocked right now (None = trading); one answer for every pane."""
    if lg.kill.get("engaged"):
        return "kill switch"
    if b.exhausted:
        return "sleeve exhausted"
    if L.ENVELOPE.check_daily_loss(day_pnl(b, day)).tripped:
        return "daily cap hit · resumes 00:00Z"
    return None


def positions(lg: L.Ledger, now: float, account: str = ALL) -> list[dict]:
    """Fills whose interval has not settled yet at ``now`` (expiry = row ts).

    The observer only writes a row once its interval has settled, so this is
    normally empty; the pane says so rather than inventing exposure.
    """
    out = []
    mids = {r.event: r.mkt_mid for r in lg.rows if r.mkt_mid is not None}
    for b in books(lg, account):
        for d in b.fills:
            if d.ts <= now:
                continue
            mid = mids.get(d.event)
            mark = (
                Decimal(str(mid)).quantize(L.CENT, rounding=ROUND_HALF_UP)
                if mid is not None
                else d.price
            )
            value = Decimal(1) - mark if d.side == "NO" else mark
            unreal = (Decimal(d.qty) * (value - d.price) - d.fee).quantize(
                L.CENT, rounding=ROUND_HALF_UP
            )
            out.append(
                {
                    "id": f"{b.key}:{d.event}",
                    "account": b.key,
                    "instrument": d.event,
                    "side": d.side,
                    "qty": d.qty,
                    "avg_price": str(d.price),
                    "mark": str(mark),  # decision-time mid
                    "unrealized_pnl": str(unreal),
                    "expiry_ts": d.ts,
                    "expires_in_s": int(d.ts - now),
                }
            )
    return sorted(out, key=lambda p: p["expiry_ts"])


def orders(
    lg: L.Ledger,
    account: str = ALL,
    status: str | None = None,
    limit: int | None = 200,
    tickets: Sequence[dict] = (),
    templates: Sequence[dict] = (),
) -> list[dict]:
    """Every decision (plus any ticket legs) as a blotter line, newest first.

    ``templates`` are the studio template workers' orders (``engine.workers.template``),
    already in blotter shape with their own ``deployment`` + ``artifact``.
    """
    out = [
        {
            "id": f"{b.key}:{d.event}",
            "ts": d.ts,
            "account": b.key,
            "deployment": LIVE[b.key].id,
            "artifact": LIVE[b.key].hash[:12],
            "instrument": d.event,
            "side": d.side,
            "qty": d.qty,
            "requested": str(d.requested),
            "notional": str(d.stake),
            "price": str(d.price) if d.status == "FILLED" else None,
            "order_id": d.order_id,
            "fee": str(d.fee),
            "pnl": str(d.pnl) if d.status == "FILLED" else None,
            "status": d.status.lower(),
            "clamped": d.clamped,
            "reason": d.reason,
            "source": "strategy",
            "parent_id": None,
        }
        for b in books(lg, account)
        for d in b.decisions
        if status is None or d.status.lower() == status
    ]
    out += [
        t
        for t in (*tickets, *templates)
        if account in (ALL, t["account"]) and (status is None or t["status"] == status)
    ]
    out.sort(
        key=lambda o: (o["ts"], ORDER.get(o["account"], 99), o.get("id", o.get("leg_id", ""))),
        reverse=True,
    )
    return out[:limit] if limit else out


def risk(lg: L.Ledger, now: float, account: str = ALL) -> list[dict]:
    day = today(now)
    floor = L.MIN_STAKE + L.fee_for(L.MIN_STAKE)
    out = []
    for b in books(lg, account):
        fills_today = [d for d in b.fills if L._day(d.ts) == day]
        out.append(
            {
                "account": b.key,
                "max_order_value": str(L.ENVELOPE.max_order_value),
                "largest_order_today": str(max((d.stake for d in fills_today), default=Decimal(0))),
                "daily_pnl": str(day_pnl(b, day)),
                "daily_loss_used": str(max(Decimal(0), -day_pnl(b, day))),
                "max_daily_loss": str(L.ENVELOPE.max_daily_loss),
                "equity": str(b.equity),
                "sleeve_floor": str(floor),
                "clamps": sum(1 for d in b.fills if d.clamped),
                "halt": halt(lg, b, day),
            }
        )
    return out
