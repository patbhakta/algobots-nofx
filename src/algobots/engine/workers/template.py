"""Paper runner for strategy-studio template deployments (ALG-3281, A11-2).

Run as its own OS process, one per deployment, under the A06 supervisor:
``python -m algobots.engine.workers.template --deployment dep-1a2b3c4d-eq-a``.

The worker reads its deployment from ``studio.json`` **once**, re-freezes the
copied params and refuses to run unless they hash to the recorded artifact, so
a template edit (which only appends a new version) can never reach it. Then:

- ``trend`` / ``range_rsi``: on every newly closed bar of the deployment's
  symbol and cadence, evaluate the frozen DSL spec (``strategies.eval``) and
  go long the whole sleeve on entry, flat on exit. Long-only.
- ``etf_alloc``: a rebalancer over hourly prices: buy the target weights on
  the first bar, then at each weekly/monthly/quarterly boundary rebalance to
  target if any weight drifted beyond the band.

Fills are simulated at the bar close, commission-free; prices come from
``demo.bars`` (synthetic, labelled). Trading starts with the first bar that
closes after the deployment was created: no backfilled history. While the
kill switch is engaged, entries and buys are recorded ``blocked`` with qty 0.

Durable state is the append-only order log
``<state_dir>/templates/<deployment>.jsonl`` plus a bar cursor; every order
carries ``deployment`` + ``artifact``. On restart the worker rebuilds its book
from the log (``reconciling``) before it may trade (``ready``). Order IDs are
deterministic per bar, so a crash between the log and the cursor can't double
an order. Liveness goes to ``<state_dir>/workers/<deployment>.json``.

Stdlib + pydantic only (no Nautilus): the API imports ``load_orders``/``book``.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

from algobots.demo import bars as BARS
from algobots.demo import killswitch
from algobots.demo import studio as S
from algobots.engine.workers.lease import EXIT_DENIED, Lease, LeaseDenied
from algobots.strategies import dsl
from algobots.strategies.eval import evaluate

CENT = Decimal("0.01")
LOT = Decimal("0.0001")  # fractional shares, as paper equities brokers allow
ZERO = Decimal(0)
MAX_CATCHUP = 2000  # bars evaluated per step after a long outage; older ones are skipped
ALLOC_CADENCE = "1h"
PERIOD = {
    "weekly": lambda d: d.strftime("%G-W%V"),
    "monthly": lambda d: d.strftime("%Y-%m"),
    "quarterly": lambda d: f"{d.year}-Q{(d.month - 1) // 3 + 1}",
}


class Tampered(RuntimeError):
    """The deployment's frozen params no longer hash to its recorded artifact."""


def is_template(d: S.Deployment) -> bool:
    return S.DEFINITIONS[d.definition].kind != "live"


def orders_path(state_dir: Path | str, dep_id: str) -> Path:
    return Path(state_dir) / "templates" / f"{dep_id}.jsonl"


def _cursor_path(state_dir: Path | str, dep_id: str) -> Path:
    return Path(state_dir) / "templates" / f"{dep_id}.cursor"


def read_log(path: Path) -> list[dict]:
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue  # a torn final line from a crash mid-append
    return out


def load_orders(state_dir: Path | str, accounts: set[str] | None = None) -> list[dict]:
    """Every template order on disk, oldest first, optionally narrowed to accounts."""
    root = Path(state_dir) / "templates"
    out = [
        o
        for p in (sorted(root.glob("*.jsonl")) if root.is_dir() else [])
        for o in read_log(p)
        if accounts is None or o.get("account") in accounts
    ]
    return sorted(out, key=lambda o: (o["ts"], o["id"]))


# --- the book: a pure replay of the order log --------------------------------------


@dataclass
class Book:
    allocation: Decimal
    cash: Decimal
    qty: dict[str, Decimal] = field(default_factory=dict)
    cost: dict[str, Decimal] = field(default_factory=dict)  # avg entry price per symbol
    realized: Decimal = ZERO
    filled: int = 0
    last_n: int | None = None
    last_px: dict[str, Decimal] = field(default_factory=dict)

    def apply(self, o: dict) -> None:
        self.last_n = max(self.last_n if self.last_n is not None else o["n"], o["n"])
        if o["status"] != "filled":
            return
        sym, q, px = o["instrument"], Decimal(o["qty"]), Decimal(o["price"])
        held = self.qty.get(sym, ZERO)
        self.last_px[sym] = px
        self.filled += 1
        if o["side"] == "BUY":
            self.cost[sym] = (self.cost.get(sym, ZERO) * held + px * q) / (held + q)
            self.qty[sym] = held + q
            self.cash -= px * q
        else:
            self.realized += (px - self.cost[sym]) * q
            self.cash += px * q
            self.qty[sym] = held - q
            if not self.qty[sym]:
                del self.qty[sym], self.cost[sym]

    def equity(self, marks: dict[str, Decimal]) -> Decimal:
        return self.cash + sum(
            (marks.get(s, self.last_px.get(s, ZERO)) * q for s, q in self.qty.items()), ZERO
        )


def book(dep: S.Deployment, orders: list[dict]) -> Book:
    b = Book(Decimal(dep.allocation), Decimal(dep.allocation))
    for o in orders:
        if o["deployment"] == dep.id:
            b.apply(o)
    return b


def marks(dep: S.Deployment, now: float) -> dict[str, Decimal]:
    """Mark prices at the last closed bar for the deployment's symbols."""
    cadence = dep.params.get("cadence", ALLOC_CADENCE)
    syms = dep.params["weights"] if dep.definition == "etf_alloc" else [dep.params["symbol"]]
    n = BARS.last_closed(cadence, now)
    return {s: Decimal(str(BARS.close(s, cadence, n))) for s in syms}


def positions(st: S.Studio, orders: list[dict], now: float, account: str = "all") -> list[dict]:
    """Open template positions, marked at the last closed bar; same shape as the blotter's."""
    out = []
    for d in st.deployments:
        if not is_template(d) or account not in ("all", d.account):
            continue
        b, mk = book(d, orders), marks(d, now)
        for sym, q in sorted(b.qty.items()):
            m = mk.get(sym, b.last_px[sym])
            out.append(
                {
                    "id": f"{d.id}:{sym}",
                    "account": d.account,
                    "deployment": d.id,
                    "artifact": d.hash[:12],
                    "instrument": sym,
                    "side": "LONG",
                    "qty": str(q),
                    "avg_price": str(b.cost[sym].quantize(CENT)),
                    "mark": str(m),
                    "unrealized_pnl": str(((m - b.cost[sym]) * q).quantize(CENT)),
                }
            )
    return out


def summary(st: S.Studio, orders: list[dict], now: float) -> dict[str, dict]:
    """Per paper account: allocated, marked equity, net P&L, deployments, orders."""
    out: dict[str, dict] = {}
    for d in st.deployments:
        if not is_template(d):
            continue
        b = book(d, orders)
        a = out.setdefault(
            d.account, {"allocated": ZERO, "equity": ZERO, "deployments": [], "orders": 0}
        )
        a["allocated"] += b.allocation
        a["equity"] += b.equity(marks(d, now))
        a["deployments"].append(d)
        a["orders"] += sum(1 for o in orders if o["deployment"] == d.id)
    for a in out.values():
        a["equity"] = a["equity"].quantize(CENT)
        a["pnl"] = a["equity"] - a["allocated"]
    return out


# --- the runner ----------------------------------------------------------------------


class TemplateRunner:
    def __init__(self, dep: S.Deployment, state_dir: Path | str) -> None:
        if not is_template(dep):
            raise ValueError(f"{dep.id} is a live demo deployment, not a template")
        if S.freeze(dep.definition, dep.params, dep.version).hash != dep.hash:
            raise Tampered(f"{dep.id}: params do not hash to artifact {dep.hash[:12]}")
        self.dep, self.state_dir = dep, Path(state_dir)
        model = S.DEFINITIONS[dep.definition].params.model_validate(dep.params)
        self.spec: dsl.StrategySpec | None = model.spec()
        self.cadence = dep.params.get("cadence", ALLOC_CADENCE)
        if self.spec is not None:
            warm = dsl.min_warmup(self.spec)
            self.window = max(3 * warm, warm + 30)  # fixed: same window -> same answer
        self.log = orders_path(state_dir, dep.id)
        self.cursor = _cursor_path(state_dir, dep.id)
        self.book = Book(Decimal(dep.allocation), Decimal(dep.allocation))
        self.seen: set[str] = set()
        self.first_n = BARS.last_closed(self.cadence, dep.created_ts) + 1
        self.reconciled = False
        self.bars_seen = 0
        self.started_at = time.time()
        self.ready_at: float | None = None

    def reconcile(self) -> int:
        """Rebuild the book from the durable log; returns orders replayed."""
        orders = read_log(self.log)
        self.book = book(self.dep, orders)
        self.seen = {o["id"] for o in orders}
        try:
            cur = int(self.cursor.read_text())
        except (FileNotFoundError, ValueError):
            cur = None
        known = [x for x in (cur, self.book.last_n) if x is not None]
        self.book.last_n = max(known) if known else None
        self.reconciled = True
        self.ready_at = time.time()
        return len(orders)

    def step(self, now: float, killed: bool = False) -> list[dict]:
        """Process bars closed since the last step; append and return the new orders."""
        if not self.reconciled:
            raise RuntimeError("reconcile() before trading")
        last = BARS.last_closed(self.cadence, now)
        start = max(self.first_n, last - MAX_CATCHUP + 1)
        if self.book.last_n is not None:
            start = max(start, self.book.last_n + 1)
        made: list[dict] = []
        self.log.parent.mkdir(parents=True, exist_ok=True)
        for n in range(start, last + 1):
            new = self._signal(n, killed) if self.spec else self._rebalance(n, killed)
            for o in new:
                if o["id"] in self.seen:
                    continue
                self.seen.add(o["id"])
                self.book.apply(o)
                made.append(o)
            self.book.last_n = n
            self.bars_seen += 1
        if made:
            with self.log.open("a") as fh:
                fh.writelines(json.dumps(o) + "\n" for o in made)
                fh.flush()
                os.fsync(fh.fileno())
        if self.book.last_n is not None:
            tmp = self.cursor.with_suffix(".tmp")
            tmp.write_text(str(self.book.last_n))
            tmp.replace(self.cursor)
        return made

    def _order(
        self, n: int, sym: str, side: str, qty: Decimal, px: Decimal, why: str, blocked: bool
    ) -> dict:
        d = self.dep
        filled = not blocked and qty > 0
        pnl = (px - self.book.cost[sym]) * qty if side == "SELL" and filled else None
        return {
            "id": f"{d.id}:{n}:{sym}:{side}",
            "n": n,
            "ts": BARS.bar_ts(self.cadence, n),
            "account": d.account,
            "deployment": d.id,
            "artifact": d.hash[:12],
            "version": d.version,
            "definition": d.definition,
            "instrument": sym,
            "side": side,
            "qty": str(qty) if filled else "0",
            "requested": str((px * qty).quantize(CENT)),
            "notional": str((px * qty).quantize(CENT)) if filled else "0.00",
            "price": str(px) if filled else None,
            "fee": "0.00",
            "pnl": str(pnl.quantize(CENT)) if pnl is not None else None,
            "status": "filled" if filled else "blocked",
            "clamped": False,
            "reason": why + (" · kill switch" if blocked else ""),
            "source": BARS.SOURCE,
        }

    def _signal(self, n: int, killed: bool) -> list[dict]:
        sym = self.dep.params["symbol"]
        ev = evaluate(self.spec, BARS.bars(sym, self.cadence, n, self.window))
        px = Decimal(str(BARS.close(sym, self.cadence, n)))
        held = self.book.qty.get(sym, ZERO)
        name = S.DEFINITIONS[self.dep.definition].name
        if not held and ev.entry:
            qty = (self.book.cash / px).quantize(LOT, rounding=ROUND_DOWN)
            if qty > 0:
                return [self._order(n, sym, "BUY", qty, px, f"{name} entry", killed)]
        elif held and ev.exit:
            return [self._order(n, sym, "SELL", held, px, f"{name} exit", False)]  # exits allowed
        return []

    def _rebalance(self, n: int, killed: bool) -> list[dict]:
        p = self.dep.params
        weights = {s: Decimal(str(w)) for s, w in p["weights"].items()}
        px = {s: Decimal(str(BARS.close(s, self.cadence, n))) for s in weights}
        if self.book.filled or self.book.qty:
            when = datetime.fromtimestamp(BARS.bar_ts(self.cadence, n), UTC)
            before = datetime.fromtimestamp(BARS.bar_ts(self.cadence, n - 1), UTC)
            key = PERIOD[p["rebalance"]]
            if key(when) == key(before):
                return []
            eq = self.book.equity(px)
            held = self.book.qty
            drift = {s: abs(held.get(s, ZERO) * px[s] / eq - w) for s, w in weights.items()}
            worst = max(drift, key=drift.get)
            if drift[worst] <= Decimal(str(p["drift_band"])):
                return []
            why = f"{p['rebalance']} rebalance · {worst} drift {drift[worst] * 100:.1f}%"
        else:
            why = "initial allocation"
        eq = self.book.equity(px)
        target = {
            s: (eq * w / px[s]).quantize(LOT, rounding=ROUND_DOWN) for s, w in weights.items()
        }
        sells = [(s, self.book.qty.get(s, ZERO) - t) for s, t in target.items()]
        out = [self._order(n, s, "SELL", q, px[s], why, False) for s, q in sells if q > 0] + [
            self._order(n, s, "BUY", -q, px[s], why, killed) for s, q in sells if q < 0
        ]
        return out

    def heartbeat(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        mk = marks(self.dep, now)
        status = {
            "account": self.dep.id,
            "deployment": self.dep.id,
            "paper_account": self.dep.account,
            "artifact": self.dep.hash[:12],
            "order_id_tag": self.dep.id,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "last_heartbeat": now,
            "ready_at": self.ready_at,
            "phase": "ready" if self.reconciled else "reconciling",
            "reconciled": self.reconciled,
            "intervals": self.bars_seen,
            "orders_submitted": len(self.seen),
            "orders_filled": self.book.filled,
            "open_positions": len(self.book.qty),
            "equity": str(self.book.equity(mk).quantize(CENT)),
            "mode": "paper",
            "source": BARS.SOURCE,
        }
        path = self.state_dir / "workers" / f"{self.dep.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status))
        tmp.replace(path)
        return status


def main(argv: list[str] | None = None) -> None:
    from algobots.api.config import get_settings

    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # --account: the supervisor's generic flag; for templates the key is the deployment id
    ap.add_argument("--deployment", "--account", dest="deployment", required=True)
    ap.add_argument("--poll", type=float, default=15.0, help="bar poll interval, seconds")
    ap.add_argument("--once", action="store_true", help="process closed bars once and exit")
    a = ap.parse_args(argv)
    dep = next((d for d in S.load(s.demo_state_dir).deployments if d.id == a.deployment), None)
    if dep is None:
        raise SystemExit(f"unknown deployment {a.deployment!r}")
    lease = Lease(Path(s.demo_state_dir), dep.id)
    try:
        lease.acquire()
    except LeaseDenied as e:
        print(f"denied: {e}", flush=True)
        raise SystemExit(EXIT_DENIED) from None
    w = TemplateRunner(dep, s.demo_state_dir)
    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        w.heartbeat()  # reconciling: entry-frozen
        w.reconcile()
        while True:
            w.step(time.time(), bool(killswitch.read(s.demo_state_dir).get("engaged")))
            w.heartbeat()
            if a.once or stop:
                break
            deadline = time.monotonic() + a.poll
            while not stop and time.monotonic() < deadline:
                time.sleep(0.2)
    finally:
        lease.release(os.getpid())


if __name__ == "__main__":
    main()
