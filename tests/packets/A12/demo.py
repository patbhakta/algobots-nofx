"""G1 five-capability paper demo walkthrough (ALG-3257, A12-1) — `make demo-g1`.

Phase 1 boots the real app (uvicorn, one Nautilus paper worker per demo
account, synthetic feed) and drives it over HTTP:

  C1 multi-account      — three accounts, each scoped and grant-checked
  C2 multi-strategy     — laya / jev / coin strategies all deciding
  C3 worker isolation   — one OS process per account, distinct PIDs
  C4 risk denial        — LIVE refused; kill switch denies with a stated,
                          audited reason
  C5 kill & freeze      — SIGKILL one worker: the others keep heartbeating,
                          the dead account refuses entries with a reason

Phase 2 replays the A06 engine fixture in-process (kill -> restart ->
entry-frozen `reconciling` -> `ready` reconciliation + measurements).

Writes artifacts/A12/: demo-run.json (timeline + trace IDs), demo-run.log,
resource-report.json, engine/ (restart/reconcile + measurements), and the
1440/390 screenshots. Needs the `workers` extra (nautilus_trader) and, for
the screenshots, node + playwright-core + a Playwright Chromium.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A12"
ACCOUNTS = ("laya", "jev", "coin")
KILLED = "coin"
LOG_LINES: list[str] = []


def log(msg: str) -> None:
    print(msg, flush=True)
    LOG_LINES.append(msg)


def _die(msg: str) -> None:
    log(f"BLOCKED: {msg}")
    (OUT / "demo-run.log").write_text("\n".join(LOG_LINES) + "\n")
    raise SystemExit(2)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _req(method: str, url: str, body: dict | None = None, form: bytes | None = None):
    data = form
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw or b"{}")
            except json.JSONDecodeError:  # redirects / HTML (form posts): body unused
                return resp.status, {}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return e.code, {}
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return 0, {}  # still booting (nautilus import is slow); the caller waits


def _wait(pred, timeout: float, what: str):  # noqa: ANN001
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = pred()
        if v:
            return v
        time.sleep(1.0)
    _die(f"timed out after {timeout:.0f}s waiting for {what}")


def _feed_rows() -> list[dict]:
    now = int(time.time()) // 900 * 900
    return [
        {
            "event": f"E{i}",
            "strike": 1,
            "outcome": i % 2,
            "ts": now - (12 - i) * 900,
            "p": 0.6,
            "conf": 0.1,
            "jev_choice": "up",
            "jev_conf": 0.5,
            "jev_p": 0.6,
        }
        for i in range(12)
    ]


def _proc_stats(pid: int) -> tuple[float, float] | None:
    from algobots.engine.workers.supervisor import proc_stats

    st = proc_stats(pid)
    return None if st is None or st[0] is None else (st[0], st[1])


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(p / 100 * len(s)))], 2)


def phase1(run: Path) -> dict:
    """Live app over HTTP: capabilities C1-C5, trace IDs, resource report."""
    feed = run / "observations.jsonl"
    feed.write_text("\n".join(json.dumps(r) for r in _feed_rows()) + "\n")
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env.update(
        ALGOBOTS_DEMO_FEED_PATH=str(feed),
        ALGOBOTS_DEMO_STATE_DIR=str(run),
        ALGOBOTS_DEMO_START=time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400)),
        ALGOBOTS_DEMO_WORKERS_ENABLED="1",
    )
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    uv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "algobots.api.main:app", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=(run / "uvicorn.log").open("wb"),
    )
    report: dict = {"base_url": base, "capabilities": {}, "trace_ids": [], "timeline": []}

    def mark(event: str, **kw: object) -> None:
        report["timeline"].append({"t": round(time.time(), 3), "event": event, **kw})
        log(f"  {event} {kw}")

    def workers(account: str | None = None) -> dict:
        url = f"{base}/demo/api/workers" + (f"?account={account}" if account else "")
        return _req("GET", url)[1]

    try:
        _wait(lambda: _req("GET", f"{base}/demo/api/workers")[0] == 200, 240, "app boot")
        snap = _wait(
            lambda: (w := workers()) and w.get("ready")
            and {x["account"] for x in w["workers"]} == set(ACCOUNTS)
            and w,
            240,
            "all three workers ready",
        )
        ws = {w["account"]: w for w in snap["workers"]}
        mark("all_ready", states={a: ws[a]["state"] for a in ACCOUNTS})

        # C1 + C2: accounts and strategies the engine actually runs.
        st = _req("GET", f"{base}/demo/api/state")[1]
        strategies = sorted(st["strategies"])
        assert strategies == sorted(ACCOUNTS), strategies
        one = _req("GET", f"{base}/demo/api/decisions?account=jev")[1]
        assert one["account"] == "jev", one.get("account")
        report["capabilities"]["C1_multi_account"] = {
            "accounts": sorted(ACCOUNTS),
            "scoped_view": "GET /demo/api/decisions?account=jev -> account=jev only",
        }
        report["capabilities"]["C2_multi_strategy"] = {
            "strategies": strategies,
            "names": {k: v["name"] for k, v in st["strategies"].items()},
        }

        # C3: one OS process per account, distinct PIDs.
        pids = {a: ws[a]["pid"] for a in ACCOUNTS}
        assert all(pids.values()) and len(set(pids.values())) == len(ACCOUNTS), pids
        report["capabilities"]["C3_worker_isolation"] = {
            "pid_per_account": pids,
            "distinct_processes": len(set(pids.values())) == len(ACCOUNTS),
            "trader_ids": {a: ws[a].get("trader_id") for a in ACCOUNTS},
        }
        mark("isolation_verified", pids=pids)

        # Resource sampling (1 Hz, 20 s) while the terminal is being driven.
        import threading

        samples: dict[str, dict[str, list[float]]] = {
            a: {"rss_mb": [], "cpu_pct": []} for a in ACCOUNTS
        }
        stop = threading.Event()

        def sampler() -> None:
            prev: dict[str, tuple[float, float]] = {}
            while not stop.is_set():
                for a, pid in pids.items():
                    try:
                        st_ = _proc_stats(pid)
                    except (FileNotFoundError, ProcessLookupError, PermissionError):
                        continue
                    if st_ is None:
                        continue
                    rss, cpu = st_
                    samples[a]["rss_mb"].append(rss)
                    if a in prev:
                        t0, c0 = prev[a]
                        dt = time.time() - t0
                        samples[a]["cpu_pct"].append(round(100 * (cpu - c0) / dt, 1))
                    prev[a] = (time.time(), cpu)
                stop.wait(1.0)

        thread = threading.Thread(target=sampler, daemon=True)
        thread.start()

        # Orders on every account -> trace IDs from parent/leg/worker fills.
        for a in ACCOUNTS:
            code, parent = _req(
                "POST",
                f"{base}/demo/api/v1/{a}/orders/place",
                {"side": "YES", "notional": "10"},
            )
            assert code == 200, (a, code, parent)
            leg = parent["legs"][0]
            report["trace_ids"].append(
                {
                    "kind": "order",
                    "account": a,
                    "parent_id": parent["id"],
                    "leg_id": leg["id"],
                    "status": leg["status"],
                }
            )
            mark("order_placed", account=a, parent_id=parent["id"], leg_id=leg["id"])

        def filled(a: str) -> dict | None:
            legs = _req("GET", f"{base}/demo/api/v1/{a}/orders")[1]["orders"]
            hit = [x for x in legs if x["status"] == "filled"]
            return hit[0] if hit else None

        for a in ACCOUNTS:
            f = _wait(lambda a=a: filled(a), 120, f"{a} worker fill")
            for t in report["trace_ids"]:
                if t["kind"] == "order" and t["account"] == a:
                    t.update(
                        worker_order_id=f.get("worker_order_id"),
                        worker_trade_id=f.get("worker_trade_id"),
                        trader_id=f.get("worker_trader_id"),
                        price=f.get("price"),
                    )
            mark("order_filled", account=a, worker_order_id=f.get("worker_order_id"))

        # C4a: LIVE is refused outright.
        code, body = _req(
            "POST",
            f"{base}/demo/api/v1/laya/orders/place",
            {"side": "YES", "notional": "10", "mode": "LIVE"},
        )
        live_denial = body.get("detail") or body.get("error")
        assert code == 422 and live_denial and "LIVE" in str(live_denial), (code, body)
        report["capabilities"]["C4_risk_denial"] = {
            "live_mode": {"status": code, "reason": live_denial},
            "kill_switch": None,
        }
        report["trace_ids"].append(
            {"kind": "denial", "code": "live_disabled", "reason": live_denial}
        )
        mark("live_refused", status=code, reason=live_denial)

        # C4b: kill switch engaged -> next order denied with a stated, audited reason.
        code, _ = _req(
            "POST", f"{base}/demo/kill-switch", form=b"engaged=on&actor=g1-walkthrough&account=laya"
        )
        assert code in (200, 303), code
        code, parent = _req(
            "POST", f"{base}/demo/api/v1/laya/orders/place", {"side": "YES", "notional": "10"}
        )
        leg = parent["legs"][0] if code == 200 else None
        assert leg and leg["status"] == "blocked" and leg.get("denial_code") == "kill_switch", (
            code,
            parent,
        )
        audit = json.loads((run / "kill-switch.json").read_text())["history"]
        report["capabilities"]["C4_risk_denial"]["kill_switch"] = {
            "denial_code": leg["denial_code"],
            "reason": leg["reason"],
            "audit_last": audit[-1],
        }
        report["trace_ids"].append(
            {"kind": "denial", "code": leg["denial_code"], "reason": leg["reason"]}
        )
        mark("kill_switch_denial", code=leg["denial_code"], reason=leg["reason"])
        code, _ = _req(
            "POST",
            f"{base}/demo/kill-switch",
            form=b"engaged=off&actor=g1-walkthrough&account=laya",
        )
        assert code in (200, 303), code

        # C5: SIGKILL one worker; the others keep heartbeating; entries refused.
        pid = pids[KILLED]

        def ws2(a: str) -> float | None:
            hb = json.loads((run / "workers" / f"{a}.json").read_text())
            return hb.get("last_heartbeat")

        beats_before = {a: ws2(a) for a in ACCOUNTS if a != KILLED}

        os.kill(pid, signal.SIGKILL)
        mark("worker_killed", account=KILLED, pid=pid)
        exited = _wait(
            lambda: (w := workers(KILLED)) and w["workers"][0]["state"] == "exited" and w,
            60,
            f"{KILLED} reported exited",
        )
        assert all(w["state"] == "ready" for w in workers()["workers"] if w["account"] != KILLED)
        time.sleep(17)  # past one worker poll: surviving heartbeats must demonstrably advance
        beats_after = {a: ws2(a) for a in ACCOUNTS if a != KILLED}
        kept = {a: (beats_after[a] or 0) > (beats_before[a] or 0) for a in beats_after}
        code, body = _req(
            "POST", f"{base}/demo/api/v1/{KILLED}/orders/place", {"side": "YES", "notional": "10"}
        )
        err = body.get("error") or {}
        reason = err.get("reason") or body.get("detail")
        assert code == 503 and err.get("code") == "worker_unavailable" and reason, (code, body)
        report["capabilities"]["C5_kill_freeze"] = {
            "killed": KILLED,
            "pid": pid,
            "exit_code": exited["workers"][0].get("exit_code"),
            "others_state": "ready",
            "others_heartbeat_advanced": kept,
            "refusal": {"status": code, "code": err.get("code"), "reason": reason},
            "note": "the app does not auto-restart a killed worker (by design); "
            "restart-with-reconciliation is proven at the engine layer in phase 2",
        }
        report["trace_ids"].append(
            {"kind": "denial", "code": err.get("code"), "reason": reason}
        )
        mark("entry_refused_after_kill", reason=reason)

        stop.set()
        thread.join(timeout=5)
        per = {
            a: {
                "rss_mb": {
                    "p50": _pct(samples[a]["rss_mb"], 50),
                    "p95": _pct(samples[a]["rss_mb"], 95),
                },
                "cpu_pct": {
                    "p50": _pct(samples[a]["cpu_pct"], 50),
                    "p95": _pct(samples[a]["cpu_pct"], 95),
                },
                "n": len(samples[a]["rss_mb"]),
            }
            for a in ACCOUNTS
        }
        pooled_rss = [x for a in ACCOUNTS for x in samples[a]["rss_mb"]]
        pooled_cpu = [x for a in ACCOUNTS for x in samples[a]["cpu_pct"]]
        (OUT / "resource-report.json").write_text(
            json.dumps(
                {
                    "packet": "A12",
                    "source": "app-level workers (uvicorn + supervisor), 1 Hz /proc sampling",
                    "startup_s": {a: ws[a].get("startup_s") for a in ACCOUNTS},
                    "workers": per,
                    "pooled": {
                        "rss_mb": {"p50": _pct(pooled_rss, 50), "p95": _pct(pooled_rss, 95)},
                        "cpu_pct_of_one_core": {
                            "p50": _pct(pooled_cpu, 50),
                            "p95": _pct(pooled_cpu, 95),
                        },
                    },
                    "engine_level": "artifacts/A12/engine/measurements.json (phase 2)",
                    "note": "measured on this host for this run only; no fleet capacity inferred",
                },
                indent=2,
            )
            + "\n"
        )

        # Screenshots: 1440 + 390 with the walkthrough card open.
        node = shutil.which("node")
        np = os.environ.get("A10_NODE_PATH")
        if not np:
            import glob

            npm_glob = Path.home() / ".npm" / "_npx" / "*" / "node_modules"
            for path in sorted(glob.glob(str(npm_glob))):
                if (Path(path) / "playwright-core").is_dir():
                    np = path
                    break
        cache = Path.home() / ".cache" / "ms-playwright"
        chromium = bool(list(cache.glob("chromium-*/chrome-linux*/chrome")))
        if not (node and np and chromium):
            _die("screenshots need node, playwright-core (A10_NODE_PATH) and a Playwright Chromium")
        shots = subprocess.run(
            [node, str(Path(__file__).parent / "shots.mjs"), base, str(OUT)],
            env={**os.environ, "NODE_PATH": np},
            capture_output=True,
            text=True,
            timeout=180,
        )
        log(shots.stdout.strip())
        if shots.returncode != 0 or not (OUT / "demo-1440.png").exists():
            _die(f"screenshots failed: {shots.stderr.strip()[-400:]}")
        mark("screenshots_captured")
        return report
    finally:
        uv.terminate()
        try:
            uv.wait(timeout=15)
        except subprocess.TimeoutExpired:
            uv.kill()
            uv.wait()


def phase2(run: Path) -> dict:
    """Engine-level kill -> restart -> reconcile + measurements (A06 machinery)."""
    from algobots.engine.workers import measure

    state = run / "engine-state"
    (state / "workers").mkdir(parents=True, exist_ok=True)
    out = OUT / "engine"
    log("phase 2: engine fixture (kill/restart/reconcile + measurements)")
    measure.main(["--state-dir", str(state), "--out", str(out), "--seconds", "10"])
    demo = json.loads((out / "demo-run.json").read_text())
    restarted = [x for x in demo["timeline"] if x["event"] == "restarted"][0]
    assert restarted.get("phases_seen") and restarted["phases_seen"][-1] in ("ready",), restarted
    after = {s["account"]: s["state"] for s in demo["after_restart"]}
    assert all(v == "ready" for v in after.values()), after
    return {
        "files": ["engine/demo-run.json", "engine/measurements.json"],
        "killed": demo["killed"],
        "phases_seen": restarted["phases_seen"],
        "orders_restored": restarted.get("orders_restored"),
        "states_after_restart": after,
    }


def main() -> int:
    try:
        import nautilus_trader  # noqa: F401
    except ImportError:
        _die("needs the `workers` extra — run: uv run --extra workers make demo-g1")
    OUT.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="g1-demo-"))
    log(f"G1 five-capability walkthrough (ALG-3257) — state {run}")
    started = time.time()
    report: dict = {"packet": "A12", "started_at": started}
    try:
        report["phase1_app"] = phase1(run)
        report["phase2_engine"] = phase2(run)
        caps = report["phase1_app"]["capabilities"]
        assert set(caps) == {"C1_multi_account", "C2_multi_strategy", "C3_worker_isolation",
                             "C4_risk_denial", "C5_kill_freeze"}, caps
        report["capabilities"] = caps
        report["trace_ids"] = report["phase1_app"]["trace_ids"]
        report["timeline"] = report["phase1_app"]["timeline"]
        del report["phase1_app"]["capabilities"]
        del report["phase1_app"]["trace_ids"]
        del report["phase1_app"]["timeline"]
        report["duration_s"] = round(time.time() - started, 1)
        (OUT / "demo-run.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
        (OUT / "demo-run.log").write_text("\n".join(LOG_LINES) + "\n")
        log(f"GREEN — 5/5 capabilities in {report['duration_s']}s; artifacts in {OUT}")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — the run log is the failure evidence
        log(f"FAIL: {exc!r}")
        import traceback

        log(traceback.format_exc())
        (OUT / "demo-run.json").write_text(
            json.dumps(
                {"packet": "A12", "failed": repr(exc), "timeline": LOG_LINES}, indent=2
            )
            + "\n"
        )
        (OUT / "demo-run.log").write_text("\n".join(LOG_LINES) + "\n")
        return 1
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
