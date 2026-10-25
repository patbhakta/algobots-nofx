"""Studio backtests on a frozen dataset (ALG-3418; slice 2 of ALG-3352).

A backtest replays one compiled Studio artifact over a *frozen* dataset and
executes every risk-approved entry on a Nautilus ``BacktestEngine``
(``algobots.engine.sleeve.NautilusSleeve``, the same executor the paper
ledger uses). The result keeps both identities: the artifact hash it ran and
the dataset id + content hash it ran on.

Dataset: the preserved Kalshi KXBTC15M recorder feed
(``marketdata/kalshi_observer.py`` → ``observations.jsonl``). ``freeze``
takes its *settled* rows, writes them once as canonical JSONL named by their
sha256, and never rewrites that file; ``load`` re-hashes on read and fails
closed on a mismatch. The live feed keeps growing, so "latest" is a new
snapshot (new hash) whenever a new interval settles, and an old dataset id
reproduces its old result exactly.

Strategy: ``kalshi_momentum.v1`` is replayed honestly, not read back from the
feed. For every interval, P(up) is recomputed with the observer's own
``momentum_signal`` over the settled closes *before* that interval, so the
backtest never sees an outcome it is trading. Entries abstain within
``min_edge`` of 0.50, size like the paper loop's laya worker, pass the demo
risk gate under the artifact's envelope, and fill at the recorded book
(YES ask / NO ask), or at the assumed 50c mid when the row captured no book.
``condition_dsl.v1`` needs OHLC bars, which this recorder does not have;
it is refused with the owning field rather than faked.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from algobots.demo import gate
from algobots.demo import ledger as L
from algobots.marketdata.kalshi_observer import contiguous_closes, momentum_signal
from algobots.risk import RiskEnvelope
from algobots.strategies.studio import StudioError

__all__ = [
    "DATASET_SOURCE",
    "BacktestDataset",
    "freeze",
    "load",
    "run_backtest",
]

DATASET_SOURCE = "kalshi-kxbtc15m-recorder"
SUPPORTED_INSTRUMENTS = {"KXBTC15M.KALSHI"}
CAPITAL = L.SLEEVE  # starting paper capital, as on the paper loop


@dataclass(frozen=True)
class BacktestDataset:
    id: str  # "<source>@<sha256[:12]>"
    sha256: str
    rows: list[dict[str, Any]]
    path: Path
    source: str = DATASET_SOURCE

    @property
    def name(self) -> str:
        first, last = self.rows[0], self.rows[-1]
        return (
            f"KXBTC15M recorder {_utc(_open(first))} to {_utc(float(last['close_ts']))} UTC"
            f" ({len(self.rows)} settled intervals)"
        )

    def describe(self) -> dict[str, Any]:
        first, last = self.rows[0], self.rows[-1]
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "snapshot_id": self.id if self.source == "warehouse" else None,
            "sha256": self.sha256,
            "rows": len(self.rows),
            "first_event": first["event"],
            "last_event": last["event"],
            "start": datetime.fromtimestamp(_open(first), UTC).isoformat(),
            "end": datetime.fromtimestamp(float(last["close_ts"]), UTC).isoformat(),
        }


def _open(row: dict[str, Any]) -> float:
    return float(row.get("open_ts") or float(row["close_ts"]) - 900)


def _usd(x: Decimal) -> str:
    return str(Decimal(x).quantize(L.CENT))


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M")


def _settled(raw: dict[str, Any]) -> bool:
    try:
        return int(raw["outcome"]) in (0, 1) and float(raw["close_ts"]) > 0 and bool(raw["event"])
    except (KeyError, TypeError, ValueError):
        return False


def _canonical(rows: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows
    ).encode()


def _dataset_dir(state_dir: Path) -> Path:
    return state_dir / "datasets"


def freeze(feed: Path, state_dir: Path) -> BacktestDataset:
    """Snapshot the feed's settled rows into a write-once, content-addressed file."""
    rows: list[dict[str, Any]] = []
    if feed.exists():
        for line in feed.read_text().splitlines():
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            if isinstance(raw, dict) and _settled(raw):
                rows.append(raw)
    if not rows:
        raise StudioError("dataset", f"no settled KXBTC15M intervals in the recorder feed {feed}")
    rows.sort(key=lambda r: (float(r["close_ts"]), str(r["event"])))
    body = _canonical(rows)
    digest = hashlib.sha256(body).hexdigest()
    path = _dataset_dir(state_dir) / f"{digest}.jsonl"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp{os.getpid()}")
        tmp.write_bytes(body)
        os.replace(tmp, path)
    return BacktestDataset(f"{DATASET_SOURCE}@{digest[:12]}", digest, rows, path)


def load(dataset_id: str, state_dir: Path) -> BacktestDataset:
    """Open a frozen dataset by id; a missing or altered file fails closed."""
    source, _, short = dataset_id.partition("@")
    if (
        source != DATASET_SOURCE
        or len(short) != 12
        or not all(c in "0123456789abcdef" for c in short)
    ):
        raise StudioError("dataset_id", f"unknown dataset {dataset_id!r}")
    matches = sorted(_dataset_dir(state_dir).glob(f"{short}*.jsonl"))
    if len(matches) != 1:
        raise StudioError("dataset_id", f"dataset {dataset_id!r} is not frozen on this server")
    body = matches[0].read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if matches[0].stem != digest:
        raise StudioError("dataset_id", f"dataset {dataset_id!r} failed its content-hash check")
    rows = [json.loads(line) for line in body.decode().splitlines()]
    return BacktestDataset(dataset_id, digest, rows, matches[0])


def load_warehouse(snapshot_id: str | None, root: Path, instrument_id: str) -> BacktestDataset:
    """Load only a published, hash-verified warehouse snapshot for this instrument."""
    from algobots.warehouse import Warehouse, WarehouseError

    warehouse = Warehouse(root)
    try:
        if snapshot_id is None:
            available = warehouse.list_snapshots(instrument_id)
            if not available:
                raise WarehouseError("no published warehouse snapshots for instrument")
            snapshot_id = max(available, key=lambda m: (m["event_end"], m["snapshot_id"]))[
                "snapshot_id"
            ]
        manifest, table = warehouse.load(snapshot_id)
        if manifest["instrument_id"] != instrument_id:
            raise WarehouseError("snapshot instrument does not match compiled artifact")
        rows = [row for row in table.to_pylist() if _settled(row)]
        if not rows:
            raise WarehouseError("snapshot contains no settled recorder intervals")
        if any(
            float(previous["close_ts"]) > _open(current)
            for previous, current in zip(rows, rows[1:], strict=False)
        ):
            raise WarehouseError("snapshot intervals overlap or are out of event-time order")
        return BacktestDataset(
            snapshot_id, manifest["sha256"], rows, root / manifest["path"], "warehouse"
        )
    except WarehouseError as exc:
        raise StudioError("dataset_id", str(exc)) from exc


def _row(raw: dict[str, Any], p: float) -> L.Row:
    def px(key: str) -> float | None:
        v = raw.get(key)
        return float(v) if isinstance(v, int | float) else None

    return L.Row(
        event=str(raw["event"]),
        strike=float(raw.get("strike") or 0),
        outcome=int(raw["outcome"]),
        ts=float(raw["close_ts"]),
        p=p,
        conf=0.0,
        jev_p=None,
        jev_conf=None,
        jev_choice=None,
        mkt_mid=px("mkt_mid"),
        mkt_yes_bid=px("mkt_yes_bid"),
        mkt_yes_ask=px("mkt_yes_ask"),
    )


def _check_artifact(artifact: dict[str, Any]) -> tuple[float, RiskEnvelope]:
    impl = artifact.get("implementation")
    nautilus = artifact.get("nautilus") or {}
    if impl != "kalshi_momentum.v1":
        raise StudioError(
            "signals.entry",
            f"{impl} needs an OHLC bar dataset; the KXBTC15M recorder only backtests "
            "kalshi_momentum.v1 (clear entry/exit and set decision.min_confidence)",
        )
    symbols = set(nautilus.get("instrument_ids") or [])
    if not symbols or not symbols <= SUPPORTED_INSTRUMENTS:
        raise StudioError(
            "universe.symbols", f"the recorder dataset covers {sorted(SUPPORTED_INSTRUMENTS)} only"
        )
    env = nautilus.get("risk_envelope") or {}
    envelope = RiskEnvelope(
        max_order_value=Decimal(env["max_order_value"]),
        max_daily_loss=Decimal(env["max_daily_loss"]),
    )
    return float(nautilus["params"]["min_edge"]), envelope


def run_backtest(
    artifact: dict[str, Any],
    dataset: BacktestDataset,
    executor: Callable[[str, Decimal], L.Sleeve] | None = None,
) -> dict[str, Any]:
    """Replay ``artifact`` over ``dataset``; deterministic for a given pair."""
    min_edge, envelope = _check_artifact(artifact)
    if executor is None:
        from algobots.engine.sleeve import EXECUTOR, NautilusSleeve

        executor, executor_name = NautilusSleeve, EXECUTOR
    else:
        executor_name = getattr(executor, "name", type(executor).__name__)
    account = f"bt{artifact['artifact_hash'][:8]}"
    sleeve = executor(account, CAPITAL)
    risk = gate.risk_gate(envelope)
    equity = CAPITAL
    daily: dict[str, Decimal] = {}
    curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    counts = {"intervals": 0, "scored": 0, "filled": 0, "abstain": 0, "blocked": 0, "wins": 0}
    px_sources: dict[str, int] = {}
    blocked_by: dict[str, int] = {}
    fees = Decimal(0)
    brier_sum = 0.0
    peak, max_dd = equity, Decimal(0)
    try:
        for i, raw in enumerate(dataset.rows):
            p, _conf, source = momentum_signal({}, contiguous_closes(dataset.rows[:i]))
            row = _row(raw, p)
            counts["intervals"] += 1
            if source != "none":
                counts["scored"] += 1
                brier_sum += (p - row.outcome) ** 2
            edge = p - 0.5
            if source == "none" or abs(edge) < min_edge:
                counts["abstain"] += 1
                curve.append({"ts": row.ts, "event": row.event, "equity": _usd(equity)})
                continue
            side = "YES" if edge > 0 else "NO"
            req = L._money(L.MIN_STAKE + Decimal(10) * Decimal(str(abs(edge) / 0.05)))
            day = L._day(row.ts)
            g = gate.pre_trade(
                gate.GateRequest(
                    account=account,
                    path="strategy",
                    value=req,
                    equity=equity,
                    floor=L.MIN_STAKE + L.fee_for(L.MIN_STAKE),
                    daily_pnl=daily.get(day, Decimal(0)),
                    kill_engaged=False,
                    now=L.interval_ts(row),
                    ticker=row.event,
                    fee=L.fee_for,
                ),
                risk,
            )
            if not g.allowed:
                counts["blocked"] += 1
                blocked_by[g.code or "risk"] = blocked_by.get(g.code or "risk", 0) + 1
                curve.append({"ts": row.ts, "event": row.event, "equity": _usd(equity)})
                continue
            px, px_source = L.exec_px(row, side)
            qty = L.contracts(g.approved, px)
            if qty < 1:
                counts["blocked"] += 1
                blocked_by["below_one_contract"] = blocked_by.get("below_one_contract", 0) + 1
                curve.append({"ts": row.ts, "event": row.event, "equity": _usd(equity)})
                continue
            won = (side == "YES") == (row.outcome == 1)
            x = sleeve.execute(row.event, side, row.ts, won, qty, px)
            equity = sleeve.equity
            daily[day] = daily.get(day, Decimal(0)) + x.pnl
            fees += x.fee
            counts["filled"] += 1
            counts["wins"] += int(won)
            px_sources[px_source] = px_sources.get(px_source, 0) + 1
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
            curve.append({"ts": row.ts, "event": row.event, "equity": _usd(equity)})
            trades.append(
                {
                    "event": row.event,
                    "side": side,
                    "p_up": p,
                    "qty": x.qty,
                    "price": str(x.price),
                    "px_source": px_source,
                    "fee": str(x.fee),
                    "pnl": str(x.pnl),
                    "won": won,
                    "order_id": x.client_order_id,
                }
            )
    finally:
        sleeve.close()
    filled = counts["filled"]
    return {
        "executor": executor_name,
        "engine": getattr(sleeve, "ids", {"account": account}),
        "implementation": artifact["implementation"],
        "params": {"min_edge": min_edge, "p_source": "mom3x15m/vol20 (recomputed per interval)"},
        "risk_envelope": {k: str(v) for k, v in envelope.model_dump().items() if v is not None},
        "metrics": {
            **counts,
            "starting_equity": _usd(CAPITAL),
            "ending_equity": _usd(equity),
            "pnl": _usd(equity - CAPITAL),
            "fees": _usd(fees),
            "max_drawdown": _usd(max_dd),
            "hit_rate": counts["wins"] / filled if filled else None,
            "brier": brier_sum / counts["scored"] if counts["scored"] else None,
            "px_sources": px_sources,
            "blocked_by": blocked_by,
        },
        "data_timeline": {
            "first_tick": dataset.describe()["start"],
            "last_tick": dataset.describe()["end"],
            "gap_policy": (
                "Recorder intervals: gaps are time between previous close and next open; "
                "no intra-interval tick coverage claim."
            ),
            "gaps": [
                {
                    "after": previous["event"],
                    "before": following["event"],
                    "seconds": _open(following) - float(previous["close_ts"]),
                }
                for previous, following in zip(dataset.rows, dataset.rows[1:], strict=False)
                if _open(following) > float(previous["close_ts"])
            ],
        },
        "equity_curve": curve,
        "trades": trades,
    }
