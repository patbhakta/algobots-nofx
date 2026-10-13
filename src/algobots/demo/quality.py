"""Decision quality + reflections for the demo (TradingAgents loop, ALG-3074 §6).

Decision log → settlement → reflection, scored by the S2.2 harness
(``algobots.evals.harness``). Every directional call a strategy makes on a
feed row becomes a prospective ``DecisionRecord``; a settled row settles it
(realized return ±1 for UP/DOWN) and only then writes a reflection. Pending
calls — feed rows whose ``outcome`` is still null — stay unsettled, are
counted, and never score or reflect.

The verdict is the harness's ``edge_demonstrated`` (Wilson lower bound over
the majority-label baseline of the same scored set). Nothing here claims an
edge the harness does not certify.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from algobots.contracts.memory import parse_namespace
from algobots.demo import ledger as L
from algobots.evals.harness import DecisionRecord, RandomBaseline, summarize
from algobots.evals.harness.scoring import realized_band

BREAK_EVEN = 0.5175  # 50c binary + 7% taker fee: 2p - 1 = fee/stake = 0.035
RANDOM_SEEDS = 20
CALIBRATION_EDGES = (0.0, 0.5, 0.55, 0.6, 0.7, 1.0)  # P(called side); <0.5 = call against own P
TENANT = "pat"


@dataclass(frozen=True)
class Call:
    """One directional call, before settlement (outcome None = pending)."""

    strategy: str
    event: str
    ts: float
    strike: float
    side: str  # YES (up) / NO (down)
    p_up: float
    status: str  # ledger status: FILLED / BLOCKED / PENDING
    outcome: int | None


def decision_id(strategy: str, event: str) -> str:
    return f"{strategy}:{event}"


def load_pending(path: Path, since_ts: float = 0.0) -> list[L.Row]:
    """Feed rows logged before settlement (``outcome`` null); ``load_rows`` skips these."""
    out: list[L.Row] = []
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
            if r.get("outcome") is not None or float(r["ts"]) < since_ts:
                continue
            out.append(
                L.Row(
                    event=r["event"],
                    strike=float(r["strike"]),
                    outcome=-1,  # sentinel: never read for a pending row
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
    return out


def _p_up(key: str, row: L.Row) -> float:
    """The strategy's own P(up); the coin control is 0.5 by construction."""
    if key == "laya":
        return row.p
    if key == "jev" and isinstance(row.jev_p, (int, float)):
        return float(row.jev_p)
    return 0.5


def calls(lg: L.Ledger, pending: list[L.Row] = ()) -> dict[str, list[Call]]:
    """Directional calls per strategy: settled from the ledger, then pending rows."""
    rows = {r.event: r for r in lg.rows}
    out: dict[str, list[Call]] = {k: [] for k in lg.books}
    for key, book in lg.books.items():
        for d in book.decisions:
            if d.side is None:
                continue  # abstain: no call, nothing to settle
            r = rows[d.event]
            out[key].append(
                Call(key, d.event, d.ts, r.strike, d.side, _p_up(key, r), d.status, r.outcome)
            )
        for r in pending:  # same signal the ledger would apply once it settles
            side, _, _ = L._intent(key, r)
            if side is not None:
                out[key].append(
                    Call(key, r.event, r.ts, r.strike, side, _p_up(key, r), "PENDING", None)
                )
    return out


def _record(c: Call, probs_up: float | None = None) -> DecisionRecord:
    p = c.p_up if probs_up is None else probs_up
    rec = DecisionRecord(
        decision_id=decision_id(c.strategy, c.event),
        ticker="KXBTC15M",
        trade_date=datetime.fromtimestamp(c.ts, UTC).strftime("%Y-%m-%d"),
        band="up" if c.side == "YES" else "down",
        probabilities={"up": p, "flat": 0.0, "down": 1.0 - p},
        horizon_days=1,
        model_name=c.strategy,
    )
    if c.outcome is not None:
        rec.settle(1.0 if c.outcome == 1 else -1.0, settled_at=_iso(c.ts))
    return rec


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def reflection(c: Call) -> dict | None:
    """Post-settlement reflection on one call; None while the call is pending."""
    if c.outcome is None:
        return None
    up = c.outcome == 1
    called_up = c.side == "YES"
    hit = called_up == up
    p_side = c.p_up if called_up else 1.0 - c.p_up
    brier = 2 * (c.p_up - (1.0 if up else 0.0)) ** 2  # harness 3-band scale (flat p = 0)
    if hit and p_side >= 0.6:
        lesson = "Confident and right — one hit is not evidence; keep sizing inside the envelope."
    elif hit:
        lesson = "Right on a thin edge — indistinguishable from a coin at this sample size."
    elif p_side >= 0.6:
        lesson = "Confident and wrong — overconfidence costs most under Brier; widen toward 0.5."
    else:
        lesson = "Wrong on a thin edge — near-50% calls should abstain more often."
    ns = f"investment/{TENANT}/accounts/{c.strategy}"
    parse_namespace(ns)  # S2.1 memory scope: one namespace per demo account
    return {
        "decision_id": decision_id(c.strategy, c.event),
        "strategy": c.strategy,
        "event": c.event,
        "settled_at": _iso(c.ts),
        "namespace": ns,
        "call": "UP" if called_up else "DOWN",
        "p_called": round(p_side, 4),
        "result": "UP" if up else "DOWN",
        "hit": hit,
        "brier": round(brier, 4),
        "fill_status": c.status,
        "text": (
            f"Called {'UP' if called_up else 'DOWN'} at P={p_side:.3f} vs ${c.strike:,.0f} strike; "
            f"BTC settled {'UP' if up else 'DOWN'} → {'hit' if hit else 'miss'}, "
            f"Brier {brier:.3f}. {lesson}"
        ),
    }


def _calibration(records: list[DecisionRecord]) -> list[dict]:
    buckets = []
    for lo, hi in zip(CALIBRATION_EDGES, CALIBRATION_EDGES[1:], strict=False):
        inb = [
            r
            for r in records
            if r.settled and lo <= r.probabilities[r.band] < hi + (1e-9 if hi == 1.0 else 0)
        ]
        hits = sum(1 for r in inb if realized_band(r, 0.003) == r.band)
        buckets.append(
            {
                "bucket": f"{lo:.2f}–{hi:.2f}",
                "count": len(inb),
                "mean_p": (sum(r.probabilities[r.band] for r in inb) / len(inb)) if inb else None,
                "hit_rate": hits / len(inb) if inb else None,
            }
        )
    return buckets


def _random_control(settled: list[DecisionRecord]) -> dict:
    """The known-random control over the same settled calls, across RANDOM_SEEDS seeds."""
    hits, certified = [], 0
    for seed in range(RANDOM_SEEDS):
        rb = RandomBaseline(seed=seed, bands=("up", "down"))
        recs = []
        for r in settled:
            band, probs = rb.predict(r.ticker, r.trade_date)
            x = DecisionRecord(
                decision_id=r.decision_id,
                ticker=r.ticker,
                trade_date=r.trade_date,
                band=band,
                probabilities=probs,
                horizon_days=1,
                model_name=f"random-{seed}",
            )
            x.settle(r.realized_return, settled_at=r.settled_at)
            recs.append(x)
        s = summarize(recs)
        if s.overall.hit_rate is not None:
            hits.append(s.overall.hit_rate)
        certified += bool(s.edge_demonstrated)
    return {
        "seeds": RANDOM_SEEDS,
        "mean_hit_rate": sum(hits) / len(hits) if hits else None,
        "certified": certified,
    }


def strategy_quality(key: str, cs: list[Call]) -> dict:
    records = [_record(c) for c in cs]
    s = summarize(records)
    settled = [r for r in records if r.settled]
    coin = summarize([_record(c, probs_up=0.5) for c in cs if c.outcome is not None])
    o = s.overall
    if s.edge_demonstrated:
        verdict = "EDGE DEMONSTRATED"
    elif o.count:
        verdict = "NO VALIDATED EDGE"
    else:
        verdict = "NO SETTLED DECISIONS"
    refl = [x for c in cs if (x := reflection(c)) is not None]
    return {
        "strategy": key,
        "name": L.STRATEGIES[key],
        "settled": len(settled),
        "pending": s.unsettled,
        "brier": s.brier,
        "coin_brier": coin.brier,
        "hit_rate": o.hit_rate,
        "hit_rate_wilson_95": [o.ci_low, o.ci_high] if o.ci_low is not None else None,
        "break_even": BREAK_EVEN,
        "clears_break_even": o.ci_low is not None and o.ci_low > BREAK_EVEN,
        "baseline_hit_rate": s.baseline_hit_rate,
        "edge_demonstrated": bool(s.edge_demonstrated),
        "verdict": verdict,
        "sample_size": o.count,
        "random_control": _random_control(settled),
        "calibration": _calibration(records),
        "harness": s.to_dict(),
        "reflections": list(reversed(refl[-3:])),
    }


def quality(lg: L.Ledger, pending: list[L.Row] = (), account: str | None = None) -> dict:
    """Pane data per strategy in ``lg`` (already narrowed to the caller's grants).

    ``account`` is the ``?account=`` context: one strategy key, or None / "all"
    for every account the ledger holds.
    """
    if account in (None, "all"):
        keys = list(lg.books)
    elif account in lg.books:
        keys = [account]
    else:
        raise KeyError(account)
    by = calls(lg, pending)
    return {
        "account": account or "all",
        "break_even": BREAK_EVEN,
        "random_seeds": RANDOM_SEEDS,
        "strategies": {k: strategy_quality(k, by[k]) for k in keys},
    }
