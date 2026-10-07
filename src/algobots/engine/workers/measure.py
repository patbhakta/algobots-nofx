"""A06 measurement + kill demo on the declared fixture (ALG-3259, AC1/AC5).

    python -m algobots.engine.workers.measure --state-dir D --out artifacts/A06 \\
        [--seconds 120] [--uid 65534]

Starts the four synthetic paper accounts (``fixture.FIXTURE_ACCOUNTS``, two
strategies each, so eight deployments) under the supervisor and its sandbox.
It samples every worker's RSS and CPU from ``/proc`` once a second for
``--seconds``, then SIGKILLs one worker. It shows that the other three keep
heartbeating and trading while the killed account is ``exited``, restarts it,
and records that it is entry-frozen (``reconciling``) until its own reconcile.

Writes ``measurements.json`` (p50/p95 RSS and CPU, startup, queue depth/age,
callback latency, per worker and pooled) and ``demo-run.json`` (the kill
timeline). It only reports what it measured on this host for this fixture.
It never extrapolates a fleet capacity.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import sys
import time
from pathlib import Path

from algobots.engine.workers.fixture import FIXTURE_ACCOUNTS, STRATEGIES_PER_ACCOUNT, pct
from algobots.engine.workers.supervisor import Isolation, Supervisor, proc_stats, read_heartbeat

KILLED = "syn2"


def _wait(pred, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


def _summary(xs: list[float]) -> dict:
    return {"p50": pct(xs, 50), "p95": pct(xs, 95), "max": max(xs, default=None), "n": len(xs)}


def sample(sup: Supervisor, seconds: float) -> dict[str, dict[str, list[float]]]:
    """RSS (MB) and CPU (% of one core over each 1 s step) per worker, from /proc."""
    out = {a: {"rss_mb": [], "cpu_pct": []} for a in sup.accounts}
    prev: dict[str, tuple[float, float]] = {}
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        now = time.monotonic()
        for a, p in sup.procs.items():
            st = proc_stats(p.pid)
            if st is None:
                continue
            rss, cpu = st
            out[a]["rss_mb"].append(rss)
            if a in prev:
                t0, c0 = prev[a]
                out[a]["cpu_pct"].append(round(100 * (cpu - c0) / (now - t0), 1))
            prev[a] = (now, cpu)
        time.sleep(1.0)
    return out


def worker_metrics(state: Path, acct: str) -> dict:
    hb = read_heartbeat(state, acct) or {}
    lat = hb.get("latency_samples_ms") or []
    return {
        "callback_latency_ms": _summary(lat),
        "queue_depth": hb.get("queue_depth"),
        "queue_age_ms": hb.get("queue_age_ms"),
        "per_tick_engine_ms_p95": hb.get("per_tick_engine_ms_p95"),
        "ticks": hb.get("intervals"),
        "orders_submitted": hb.get("orders_submitted"),
        "orders_filled": hb.get("orders_filled"),
        "uid": hb.get("uid"),
        "trader_id": hb.get("trader_id"),
        "strategies": hb.get("strategies"),
        "_lat": lat,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--rate", type=float, default=4.0)
    ap.add_argument("--uid", type=int, default=None)
    a = ap.parse_args(argv)
    state, out = Path(a.state_dir), Path(a.out)
    (state / "workers").mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o755)
    sup = Supervisor(
        list(FIXTURE_ACCOUNTS),
        state,
        poll=a.poll,
        command=[sys.executable, "-m", "algobots.engine.workers.fixture", "--rate", str(a.rate)],
        env={"ALGOBOTS_DEMO_STATE_DIR": str(state)},
        isolation=Isolation(uid=a.uid),
    )
    timeline: list[dict] = []

    def mark(event: str, **kw: object) -> None:
        timeline.append({"t": round(time.time(), 3), "event": event, **kw})
        print(event, kw, flush=True)

    t_start = time.time()
    sup.start()
    mark("started", accounts=sup.accounts)
    try:
        if not _wait(sup.ready, 180):
            raise SystemExit(f"workers never ready: {sup.snapshot()}")
        snap = {s["account"]: s for s in sup.snapshot()}
        mark("all_ready", startup_s={k: v["startup_s"] for k, v in snap.items()})
        before = sup.snapshot()
        samples = sample(sup, a.seconds)
        per = {acct: worker_metrics(state, acct) for acct in sup.accounts}

        # Demo: kill one worker; the rest keep going; the killed account is frozen until reconcile.
        pre = {x: (read_heartbeat(state, x) or {}).get("intervals", 0) for x in sup.accounts}
        os.kill(snap[KILLED]["pid"], signal.SIGKILL)
        mark("killed", account=KILLED, pid=snap[KILLED]["pid"])
        _wait(lambda: sup.status(KILLED).state == "exited", 15)
        time.sleep(5 * a.poll)
        after_kill = sup.snapshot()
        post = {x: (read_heartbeat(state, x) or {}).get("intervals", 0) for x in sup.accounts}
        mark(
            "after_kill",
            states={s["account"]: s["state"] for s in after_kill},
            ticks_delta={x: post[x] - pre[x] for x in sup.accounts},
        )
        sup.start(KILLED)
        phases: list[str] = []

        def seen() -> bool:
            hb = read_heartbeat(state, KILLED) or {}
            if hb.get("phase") and (not phases or phases[-1] != hb["phase"]):
                phases.append(hb["phase"])
            return hb.get("reconciled") is True

        _wait(seen, 120)
        hb = read_heartbeat(state, KILLED) or {}
        mark(
            "restarted",
            account=KILLED,
            pid=sup.status(KILLED).pid,
            phases_seen=phases,
            orders_restored=hb.get("orders_restored"),
            orders_rejected_frozen=hb.get("orders_rejected_frozen"),
        )
        after_restart = sup.snapshot()
        sandbox = {
            x: json.loads((state / "workers" / f"{x}.sandbox.json").read_text())
            for x in sup.accounts
        }
    finally:
        sup.stop()
        mark("stopped")

    rss = [v for s in samples.values() for v in s["rss_mb"]]
    cpu = [v for s in samples.values() for v in s["cpu_pct"]]
    lat = [v for m in per.values() for v in m.pop("_lat")]
    startup = [s["startup_s"] for s in before]
    workers = {
        acct: {
            "rss_mb": _summary(samples[acct]["rss_mb"]),
            "cpu_pct": _summary(samples[acct]["cpu_pct"]),
            "startup_s": next(s["startup_s"] for s in before if s["account"] == acct),
            **per[acct],
        }
        for acct in sup.accounts
    }
    measurements = {
        "packet": "A06",
        "slice": "A06-3 (ALG-3259)",
        "fixture": {
            "accounts": list(FIXTURE_ACCOUNTS),
            "strategies_per_account": STRATEGIES_PER_ACCOUNT,
            "deployments": len(FIXTURE_ACCOUNTS) * STRATEGIES_PER_ACCOUNT,
            "quote_rate_per_instrument_hz": a.rate,
            "poll_s": a.poll,
            "worker": "algobots.engine.workers.fixture (Nautilus BacktestEngine, paper venue)",
        },
        "host": {
            "python": platform.python_version(),
            "kernel": platform.release(),
            "cpus": os.cpu_count(),
            "isolation_uid": a.uid,
        },
        "window": {"started_at": t_start, "sample_seconds": a.seconds, "sample_hz": 1},
        "pooled": {
            "rss_mb": _summary(rss),
            "cpu_pct_of_one_core": _summary(cpu),
            "startup_s": _summary(startup),
            "callback_latency_ms": _summary(lat),
            "queue_depth_p95_max": max(
                (m["queue_depth"]["p95"] or 0 for m in per.values() if m["queue_depth"]),
                default=None,
            ),
            "queue_age_ms_p95_max": max(
                (m["queue_age_ms"]["p95"] or 0 for m in per.values() if m["queue_age_ms"]),
                default=None,
            ),
        },
        "workers": workers,
        "capacity_extrapolation": None,
        "note": "measured for this fixture on this host only; no fleet capacity is inferred",
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "measurements.json").write_text(json.dumps(measurements, indent=2) + "\n")
    demo = {
        "killed": KILLED,
        "timeline": timeline,
        "before_kill": before,
        "after_kill": after_kill,
        "after_restart": after_restart,
        "sandbox": sandbox,
    }
    (out / "demo-run.json").write_text(json.dumps(demo, indent=2, default=str) + "\n")


if __name__ == "__main__":
    main()
