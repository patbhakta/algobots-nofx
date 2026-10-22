"""Decision quality: append-only decision log -> settlement -> reflection.

TradingAgents patterns (ALG-3074 option A), demo scope only. Every strategy
decision is logged once (keyed ``strategy:event``) with its inputs, rating,
confidence and prompt/model receipt where one exists — never its outcome.
Settlement joins the log to the Kalshi interval outcome afterwards. The
reflection view lists recent losses with their recorded reason and a bounded
lesson slot; lessons are display-only and never reach a live decision
(the full module is ALG-3085 / S2.1).

Records keep ``contracts.decision`` field names (request_id, instrument_id,
provider, model_revision, status, answers, confidence, receipt_ref) so the
log can be lifted into ``DecisionResponse`` by S2.1 without a migration.
"""

from __future__ import annotations

import fcntl
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from algobots.contracts.decision import DecisionStatus
from algobots.demo import ledger as L

SCHEMA = "demo.decision_log/1"
LOG_FILE = "decision_log.jsonl"
LESSONS_FILE = "lessons.jsonl"
MID = 0.5  # assumed fill price, so edge per contract = hit rate - 0.50
MIN_N = 30  # below this no hit rate is distinguishable from a coin
LESSON_MAX = 280
REFLECT_N = 8

PROVIDER = {"laya": "laya-system-one", "jev": "jev-zero-shot", "coin": "sha256-coin"}


def decision_id(strategy: str, event: str) -> str:
    return f"{strategy}:{event}"


def _prob(x: object) -> float | None:
    """Feed values are untyped; anything not a probability is logged as unknown."""
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def record(d: L.Decision, row: L.Row) -> dict:
    """One log line for a decision. Holds what was known at decision time only."""
    if d.strategy == "laya":
        p, conf = _prob(row.p), _prob(row.conf)
        inputs = {"strike": row.strike, "p_up": row.p, "conf": row.conf}
    elif d.strategy == "jev":
        p, conf = _prob(row.jev_p), _prob(row.jev_conf)
        inputs = {"strike": row.strike, "jev_p": row.jev_p, "jev_conf": row.jev_conf}
        inputs["jev_choice"] = row.jev_choice
    else:
        p, conf = MID, None
        inputs = {"strike": row.strike}
    if d.side is not None:
        status = DecisionStatus.VALID
    elif d.strategy == "jev":
        status, p, conf = DecisionStatus.UNAVAILABLE, None, None
    else:
        status, conf = DecisionStatus.ABSTAIN, None
    rating = {"YES": "up", "NO": "down"}.get(d.side or "")
    p_rating = None if p is None or rating is None else (p if rating == "up" else 1 - p)
    did = decision_id(d.strategy, d.event)
    return {
        "schema": SCHEMA,
        "schema_version": "1.0",  # DecisionResponse@1.0 field names below
        "decision_id": did,
        "request_id": did,
        "strategy": d.strategy,
        "instrument_id": d.event,
        "horizon": "15m",
        "decided_at": datetime.fromtimestamp(d.ts, UTC).isoformat(),
        "provider": PROVIDER[d.strategy],
        "model_revision": None,  # the observer feed carries no model pin yet
        "receipt_ref": None,  # nor a prompt/model receipt; never invented
        "status": status.value,
        "answers": (
            [{"question_id": "direction", "value": rating, "probability": p_rating}]
            if rating
            else []
        ),
        "confidence": conf if status is DecisionStatus.VALID else None,
        "rating": rating,
        "side": d.side,
        "p_up": p,
        "inputs": inputs,
        "reason": d.reason,
        "execution": {"status": d.status, "stake": str(d.stake)},
    }


def records(lg: L.Ledger) -> list[dict]:
    by_event = {r.event: r for r in lg.rows}
    return [record(d, by_event[d.event]) for b in lg.books.values() for d in b.decisions]


def load(path: Path) -> list[dict]:
    """Log lines in append order; first write wins on a duplicate id; bad lines skipped."""
    out, seen = [], set()
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
            did = r["decision_id"]
        except (ValueError, KeyError, TypeError):
            continue
        if did not in seen:
            seen.add(did)
            out.append(r)
    return out


def ingest(path: Path, new: Iterable[dict]) -> int:
    """Append records not already logged; returns how many were written. Idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)  # concurrent page loads must not double-append
        fh.seek(0)
        seen = {r["decision_id"] for r in load(path)}
        lines = []
        for r in new:
            if r["decision_id"] not in seen:
                seen.add(r["decision_id"])
                lines.append(json.dumps(r, sort_keys=True) + "\n")
        fh.writelines(lines)
        fh.flush()
    return len(lines)


@dataclass(frozen=True)
class Settled:
    rec: dict
    outcome: int  # 1 = BTC closed above strike
    hit: bool
    brier: float
    edge: float  # $ per contract bought at the 50c mid, before fees
    market_brier: float | None = None  # (Kalshi mid - outcome)^2, same event


def settle(
    recs: Iterable[dict], outcomes: dict[str, int], mids: dict[str, float] | None = None
) -> list[Settled]:
    """Score every VALID decision whose interval has closed; others stay unsettled.

    ``mids`` carries the venue's own YES mid per event: the benchmark a
    strategy must beat is the book it trades against, scored on exactly the
    events that strategy decided (ALG-3357 honest scoreboard). An event the
    book never quoted is excluded from the market average, never guessed at.
    """
    out = []
    for r in recs:
        if r.get("status") != DecisionStatus.VALID or r.get("instrument_id") not in outcomes:
            continue
        y = outcomes[r["instrument_id"]]
        hit = (r["rating"] == "up") == (y == 1)
        p = MID if r.get("p_up") is None else float(r["p_up"])
        mid = (mids or {}).get(r["instrument_id"])
        mb = None if mid is None else (mid - y) ** 2
        out.append(Settled(r, y, hit, (p - y) ** 2, (1.0 if hit else 0.0) - MID, mb))
    return out


@dataclass(frozen=True)
class Score:
    strategy: str
    n: int
    hits: int
    hit_rate: float | None
    brier: float | None
    mean_edge: float | None
    se: float | None
    verdict: str
    proven: bool
    market_brier: float | None = None  # Kalshi mid on the same settled events
    market_n: int = 0  # settled events the book actually quoted


def score(settled: list[Settled], strategy: str) -> Score:
    xs = [s for s in settled if s.rec["strategy"] == strategy]
    n = len(xs)
    if not n:
        return Score(
            strategy, 0, 0, None, None, None, None, "no edge proven · no settled decisions", False
        )
    hits = sum(s.hit for s in xs)
    h = hits / n
    edge = sum(s.edge for s in xs) / n
    se = math.sqrt(h * (1 - h) / n)
    if n < MIN_N:
        verdict = f"no edge proven · n={n} < {MIN_N}"
    elif edge <= 0:
        verdict = "no edge proven · edge ≤ 0"
    elif edge <= 2 * se:
        verdict = "no edge proven · within 2σ of zero"
    else:
        verdict = f"edge {edge * 100:+.1f}¢ > 2σ · not yet out-of-sample"
    proven = n >= MIN_N and edge > 2 * se
    mbs = [s.market_brier for s in xs if s.market_brier is not None]
    market_brier = sum(mbs) / len(mbs) if mbs else None
    return Score(
        strategy, n, hits, h, sum(s.brier for s in xs) / n, edge, se, verdict, proven,
        market_brier, len(mbs),
    )


def load_lessons(path: Path) -> dict[str, str]:
    """``{"decision_id", "lesson"}`` lines; each lesson capped at LESSON_MAX chars."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
            out[str(r["decision_id"])] = str(r["lesson"]).strip()[:LESSON_MAX]
        except (ValueError, KeyError, TypeError):
            continue
    return out


def losses(
    settled: list[Settled], strategy: str | None = None, n: int = REFLECT_N
) -> list[Settled]:
    lost = [s for s in settled if not s.hit and strategy in (None, s.rec["strategy"])]
    return sorted(lost, key=lambda s: s.rec["decided_at"], reverse=True)[:n]


@dataclass(frozen=True)
class Clash:
    event: str
    decided_at: str
    bull: dict  # the analyst calling up
    bear: dict  # the analyst calling down
    outcome: int | None  # None = interval not settled yet

    @property
    def winner(self) -> str | None:
        if self.outcome is None:
            return None
        return (self.bull if self.outcome == 1 else self.bear)["strategy"]


@dataclass(frozen=True)
class Debate:
    """Bull/bear debate between the two analysts (TradingAgents researcher pattern).

    Laya and Jev each make an independent call per interval; where they disagree,
    the up-caller is the bull and the down-caller the bear, and settlement names
    the winner. Arguments are the reasons each analyst recorded — nothing is
    generated, and no judge's verdict reaches an order (display only).
    """

    agreed: int
    agreed_hits: int
    clashes: list[Clash]
    wins: dict[str, int]

    @property
    def settled(self) -> int:
        return sum(1 for x in self.clashes if x.outcome is not None)


DEBATERS = ("laya", "jev")


def debate(recs: Iterable[dict], outcomes: dict[str, int]) -> Debate:
    calls: dict[str, dict[str, dict]] = {}
    for r in recs:
        if r.get("strategy") in DEBATERS and r.get("status") == DecisionStatus.VALID:
            calls.setdefault(r["instrument_id"], {})[r["strategy"]] = r
    agreed = agreed_hits = 0
    clashes, wins = [], dict.fromkeys(DEBATERS, 0)
    for event, by in calls.items():
        if len(by) < len(DEBATERS):
            continue
        a, b = (by[k] for k in DEBATERS)
        y = outcomes.get(event)
        if a["rating"] == b["rating"]:
            if y is not None:
                agreed += 1
                agreed_hits += (a["rating"] == "up") == (y == 1)
            continue
        bull, bear = (a, b) if a["rating"] == "up" else (b, a)
        x = Clash(event, max(a["decided_at"], b["decided_at"]), bull, bear, y)
        if x.winner:
            wins[x.winner] += 1
        clashes.append(x)
    clashes.sort(key=lambda x: x.decided_at, reverse=True)
    return Debate(agreed, agreed_hits, clashes, wins)


@dataclass(frozen=True)
class Quality:
    logged: int
    settled: list[Settled]
    scores: dict[str, Score]
    lessons: dict[str, str]
    debate: Debate | None = None  # None unless both debaters are in scope


def quality(
    recs: list[dict],
    lg: L.Ledger,
    lessons: dict[str, str] | None = None,
    accounts: Iterable[str] | None = None,
) -> Quality:
    """Settle and score; ``accounts`` (the caller's grants) bounds every view."""
    keep = [k for k in L.STRATEGIES if accounts is None or k in set(accounts)]
    recs = [r for r in recs if r.get("strategy") in keep]
    outcomes = {r.event: r.outcome for r in lg.rows}
    mids = {r.event: r.mkt_mid for r in lg.rows if r.mkt_mid is not None}
    st = settle(recs, outcomes, mids)
    ids = {r["decision_id"] for r in recs}
    mine = {k: v for k, v in (lessons or {}).items() if k in ids}
    deb = debate(recs, outcomes) if set(DEBATERS) <= set(keep) else None
    return Quality(len(recs), st, {k: score(st, k) for k in keep}, mine, deb)


def sync(state_dir: Path, lg: L.Ledger, accounts: Iterable[str] | None = None) -> Quality:
    """Ingest the ledger's decisions into the log, then settle what the log holds."""
    path = state_dir / LOG_FILE
    ingest(path, records(lg))
    return quality(load(path), lg, load_lessons(state_dir / LESSONS_FILE), accounts)
