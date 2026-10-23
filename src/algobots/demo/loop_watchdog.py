#!/usr/bin/env python3
"""Demo-loop watchdog (ALG-3357, now ALG-3411): guards the Kalshi paper demo end-to-end.

Checks every run (stdlib only, designed for a systemd timer on .243):
  1. Feed freshness  - newest observations.jsonl row younger than FEED_MAX_AGE_S,
                       for the Kalshi feed and (when set) the Polymarket feed #2.
  2. Worker health   - /demo/api/workers: every account ready, heartbeat fresh.
  3. Day-reset proof - after 00:00 UTC, if coin was envelope-gated the previous
                       day (fewer fills than settled intervals) and a coin fill
                       appears on the new UTC day, post the proof ONCE to
                       ALG-3411 (daily-loss envelope resets automatically).
  4. Reset-missing   - coin gated yesterday + settled intervals today +
                       zero coin fills today (coin attempts an entry every
                       interval) -> ALERT that the reset did not lift.

Posting rules (anti-spam): one alert per anomaly episode, one recovery post,
re-alert at most every REALERT_S while persisting, one reset-proof per UTC day.
Everything is logged; the process always exits 0 so the timer stays healthy.

Env overrides: ALGOBOTS_FEED, ALGOBOTS_PM_FEED (empty disables), ALGOBOTS_DECISION_LOG,
ALGOBOTS_WORKERS_URL, ALGOBOTS_DECISIONS_URL,
WATCHDOG_STATE, WATCHDOG_LOG, PAPERCLIP_URL, PAPERCLIP_TOKEN_FILE, ISSUE.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

FEED = Path(os.environ.get("ALGOBOTS_FEED", "/opt/laya/kalshi/observations.jsonl"))
_PM_FEED = os.environ.get("ALGOBOTS_PM_FEED", "/opt/laya/polymarket/observations.jsonl")
PM_FEED = Path(_PM_FEED) if _PM_FEED else None
DECISION_LOG = Path(os.environ.get(
    "ALGOBOTS_DECISION_LOG",
    "/var/lib/docker/volumes/algobots_demostate/_data/decision_log.jsonl"))
WORKERS_URL = os.environ.get(
    "ALGOBOTS_WORKERS_URL", "http://100.82.57.72:8000/demo/api/workers")
DECISIONS_URL = os.environ.get(
    "ALGOBOTS_DECISIONS_URL",
    urllib.parse.urljoin(WORKERS_URL, "decisions"))
STATE_FILE = Path(os.environ.get("WATCHDOG_STATE", "/opt/laya/kalshi/loop-watchdog.state.json"))
LOG_FILE = Path(os.environ.get("WATCHDOG_LOG", "/opt/laya/kalshi/loop-watchdog.log"))
PAPERCLIP_URL = os.environ.get("PAPERCLIP_URL", "http://100.101.235.117:3100")
TOKEN_FILE = Path(os.environ.get("PAPERCLIP_TOKEN_FILE", "/root/.paperclip/jarvis-cli-token"))
# Demo-loop alerts and day-reset proofs land on the dedicated loop card;
# ALG-3357 stays blocked on the IBKR datafeed and must not be reopened.
ISSUE = os.environ.get("ISSUE", "ALG-3411")

FEED_MAX_AGE_S = 1500          # feed settles every 900s; allow one miss
HEARTBEAT_MAX_AGE_S = 120
EXPECTED_ACCOUNTS = ("laya", "jev", "coin")
REALERT_S = 6 * 3600
RESET_GRACE_MIN = 45         # reset-missing alert window opens 00:45 UTC


def log(state: dict, msg: str) -> None:
    line = f"{datetime.now(UTC).isoformat(timespec='seconds')} {msg}"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as fh:
        fh.write(line + "\n")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {"active": {}, "alerted_at": {}, "reset_proof_date": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE_FILE)


def post_comment(body: str) -> str | None:
    try:
        token = TOKEN_FILE.read_text().strip()
    except OSError:
        return "token unreadable"
    req = urllib.request.Request(
        f"{PAPERCLIP_URL}/api/issues/{ISSUE}/comments",
        data=json.dumps({"body": body}).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return None if resp.status in (200, 201) else f"HTTP {resp.status}"
    except Exception as exc:  # noqa: BLE001 - report, never crash
        return str(exc)[:200]


def feed_check(path: Path | None = None, prefix: str = "feed") -> tuple[str, int]:
    """Return (anomaly_key_or_empty, newest_row_age_s) for one observer feed."""
    path = FEED if path is None else path
    newest = 0.0
    try:
        with path.open() as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    newest = max(newest, float(row.get("ts", 0)))
                except (ValueError, TypeError):
                    continue
    except OSError:
        return f"{prefix}_unreadable", 10**9
    age = time.time() - newest
    return ("" if age <= FEED_MAX_AGE_S else f"{prefix}_stale", int(age))


def workers_check() -> tuple[str, str]:
    """Return (anomaly_key_or_empty, human summary)."""
    try:
        with urllib.request.urlopen(WORKERS_URL, timeout=10) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001
        return "workers_api_down", f"workers API unreachable: {str(exc)[:120]}"
    problems, bits = [], []
    for w in data.get("workers", []):
        acct = w.get("account", "?")
        # denied/not-started workers report heartbeat null — an anomaly to
        # REPORT, never a crash (the 2026-10-22 deny window crashed this check)
        hb = w.get("last_heartbeat")
        hb_age = time.time() - float(hb) if isinstance(hb, (int, float)) else None
        bits.append(f"{acct}={w.get('state')}/"
                    f"{f'hb{int(hb_age)}s' if hb_age is not None else 'hb-none'}/"
                    f"fills{w.get('orders_filled')}")
        if acct in EXPECTED_ACCOUNTS:
            if w.get("state") != "ready":
                problems.append(f"{acct} state={w.get('state')}")
            if hb_age is None:
                problems.append(f"{acct} heartbeat missing (worker not started)")
            elif hb_age > HEARTBEAT_MAX_AGE_S:
                problems.append(f"{acct} heartbeat {int(hb_age)}s old")
    missing = [a for a in EXPECTED_ACCOUNTS
               if a not in {w.get("account") for w in data.get("workers", [])}]
    if missing:
        problems.append(f"missing workers {missing}")
    return ("workers_unhealthy:" + ";".join(problems) if problems else "",
            "; ".join(bits))


def refresh_decisions() -> str | None:
    """Persist current ledger evidence without requiring an open demo page."""
    try:
        with urllib.request.urlopen(DECISIONS_URL, timeout=15) as resp:
            payload = json.load(resp)
        if not isinstance(payload, dict) or not isinstance(payload.get("logged"), int):
            return "decisions endpoint returned no logged count"
    except Exception as exc:  # noqa: BLE001 - health checks must keep running
        return str(exc)[:200]
    return None


def coin_fills_by_day() -> dict[str, list[dict]]:
    days: dict[str, list[dict]] = {}
    try:
        with DECISION_LOG.open() as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("strategy") != "coin":
                    continue
                if (d.get("execution") or {}).get("status") != "FILLED":
                    continue
                day = (d.get("decided_at") or "")[:10]
                if day:
                    days.setdefault(day, []).append(d)
    except OSError:
        pass
    return days


def settled_intervals_by_day() -> dict[str, int]:
    days: dict[str, int] = {}
    try:
        with FEED.open() as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("settled_ts") is None:
                    continue
                day = datetime.fromtimestamp(
                    float(row["settled_ts"]), tz=UTC).strftime("%Y-%m-%d")
                days[day] = days.get(day, 0) + 1
    except OSError:
        pass
    return days


def reset_missing_check(now: float | None = None) -> tuple[str | None, str]:
    """Anomaly when the day-reset should have lifted but coin stays silent.

    Complements ``reset_proof_check``: that posts when the reset WORKS; this
    speaks up when it silently doesn't. Coin attempts an entry every interval,
    so once the envelope lifts a fill lands within ~15 min of 00:00 UTC. If
    yesterday was demonstrably gated, the new day is already settling markets
    (>= 2, so a late-starting feed can't false-alarm) and coin still has zero
    fills, something between the gate and the fill broke - make it loud.
    """
    now = time.time() if now is None else now
    utc = datetime.fromtimestamp(now, UTC)
    if utc.hour == 0 and utc.minute < RESET_GRACE_MIN:
        return None, ""  # too soon after midnight
    fills = coin_fills_by_day()
    intervals = settled_intervals_by_day()
    today = utc.strftime("%Y-%m-%d")
    yesterday = (utc - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_fills = len(fills.get(yesterday, []))
    prev_intervals = intervals.get(yesterday, 0)
    if not (prev_intervals > 0 and prev_fills < prev_intervals):
        return None, ""  # no gating yesterday -> nothing to expect
    today_fills = len(fills.get(today, []))
    today_intervals = intervals.get(today, 0)
    if today_fills or today_intervals < 2:
        return None, ""
    detail = (f"coin gated yesterday ({prev_fills} fills / {prev_intervals} settled "
              f"intervals) but 0 fills across {today_intervals} settled intervals "
              f"today - daily-loss reset did not visibly lift (or entries blocked "
              f"another way)")
    return "envelope_reset_missing", detail


def reset_proof_check(state: dict) -> str | None:
    """Body of a proof comment if the day-reset evidence is fresh, else None."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if state.get("reset_proof_date") == today:
        return None
    fills = coin_fills_by_day()
    today_fills = fills.get(today, [])
    if not today_fills:
        return None  # nothing to prove yet
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_fills = len(fills.get(yesterday, []))
    prev_intervals = settled_intervals_by_day().get(yesterday, 0)
    if not prev_intervals or prev_fills >= prev_intervals:
        # No settled feed yesterday (can't verify gating) or no gating
        # yesterday -> today's first fill is not a day-reset event.
        state["reset_proof_date"] = today
        return None
    first = min(today_fills, key=lambda d: d.get("decided_at", ""))
    body = (
        "**JARVIS demo-loop watchdog — envelope day-reset verified (automatic).**\n\n"
        f"Coin was daily-loss-gated on {yesterday} "
        f"({prev_fills} fills vs {prev_intervals} settled intervals) and has "
        f"resumed filling on {today} with no manual reset:\n\n"
        f"- First fill after 00:00 UTC: `{first.get('decision_id')}` at "
        f"{first.get('decided_at')} — side {first.get('side')}, "
        f"stake {(first.get('execution') or {}).get('stake')} USD.\n"
        f"- Fills so far today: {len(today_fills)}.\n\n"
        "Behavior pinned by commit `fe25041`; captured by "
        "`demo-loop-watchdog.timer` (every 5 min) on .243."
    )
    state["reset_proof_date"] = today
    return body


def main() -> None:
    state = load_state()
    now = time.time()
    anomalies: dict[str, str] = {}

    key, age = feed_check()
    summary = f"feed_age={age}s"
    if key:
        anomalies[key] = f"feed newest row is {age}s old (limit {FEED_MAX_AGE_S}s)"

    if PM_FEED is not None:
        pkey, page = feed_check(PM_FEED, "pm_feed")
        summary += f" pm_feed_age={page}s"
        if pkey:
            anomalies[pkey] = (f"Polymarket feed {PM_FEED} newest row is {page}s old "
                               f"(limit {FEED_MAX_AGE_S}s)")

    wkey, wsum = workers_check()
    summary += f" workers[{wsum}]"
    if wkey:
        anomalies[wkey] = wsum

    evidence_error = refresh_decisions()
    if evidence_error:
        anomalies["decision_evidence_unavailable"] = evidence_error
    else:
        rkey, rdetail = reset_missing_check()
        if rkey:
            anomalies[rkey] = rdetail

    # Fire alerts / recoveries.
    for akey, detail in anomalies.items():
        first = akey not in state["active"]
        due = now - state["alerted_at"].get(akey, 0) >= REALERT_S
        if first or due:
            body = ("**JARVIS demo-loop watchdog ALERT** "
                    f"(`{akey}`) — {detail}. "
                    "Feed/worker check on .243; auto-posted by "
                    "demo-loop-watchdog.timer. Next re-alert in 6h if persisting.")
            err = post_comment(body)
            log(state, f"ALERT {akey} posted_err={err} detail={detail}")
            state["alerted_at"][akey] = now
    for akey in [k for k in state["active"] if k not in anomalies]:
        err = post_comment(f"**JARVIS demo-loop watchdog RECOVERED** — `{akey}` "
                           "cleared on the next check.")
        log(state, f"RECOVERED {akey} posted_err={err}")
    state["active"] = anomalies

    proof = None if evidence_error else reset_proof_check(state)
    if proof:
        err = post_comment(proof)
        log(state, f"RESET_PROOF posted_err={err}")

    if not anomalies and not proof:
        log(state, f"OK {summary}")
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never fail the timer
        print(f"watchdog crashed: {exc}", file=sys.stderr)
        try:
            load_state()  # touch nothing else; log if possible
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a") as fh:
                fh.write(f"{datetime.now(UTC).isoformat()} "
                         f"CRASH {exc}\n")
        except Exception:  # noqa: BLE001
            pass
    sys.exit(0)
