"""Unit tests for the demo-loop watchdog (ALG-3357).

Exercises the pure check functions against tmp files - no network, no
Paperclip posts. The reset-proof rule under test: a proof is only claimed
when coin was demonstrably envelope-gated yesterday (fewer fills than
settled intervals) AND a fill exists on the new UTC day.
"""

from __future__ import annotations

import json
import time

from algobots.demo import loop_watchdog as lw


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _coin_fill(day: str, when: str) -> dict:
    return {"strategy": "coin", "decided_at": f"{day}T{when}+00:00",
            "decision_id": f"coin:X-{when}", "side": "YES",
            "execution": {"status": "FILLED", "stake": "10.00"}}


def _settlement(epoch: float) -> dict:
    return {"ts": epoch, "settled_ts": epoch}


def test_reset_proof_only_when_gated_yesterday(tmp_path, monkeypatch):
    feed = tmp_path / "observations.jsonl"
    dlog = tmp_path / "decision_log.jsonl"
    monkeypatch.setattr(lw, "FEED", feed)
    monkeypatch.setattr(lw, "DECISION_LOG", dlog)

    now = time.time()
    # Yesterday (as seen by settled_ts): 4 intervals, only 2 fills -> gated.
    _write(feed, [_settlement(now - 86400 + i * 900) for i in range(4)])
    _write(dlog, [_coin_fill("2026-01-01", "01:00:00"),
                  _coin_fill("2026-01-01", "01:15:00"),
                  _coin_fill(lw.datetime.now(lw.timezone.utc).strftime("%Y-%m-%d"),
                             "00:15:00")])

    state = {"reset_proof_date": None}
    body = lw.reset_proof_check(state)
    assert body is not None and "resumed" in body
    assert state["reset_proof_date"] == lw.datetime.now(lw.timezone.utc).strftime(
        "%Y-%m-%d")
    # Idempotent per day.
    assert lw.reset_proof_check(state) is None


def test_no_proof_when_not_gated_yesterday(tmp_path, monkeypatch):
    feed = tmp_path / "observations.jsonl"
    dlog = tmp_path / "decision_log.jsonl"
    monkeypatch.setattr(lw, "FEED", feed)
    monkeypatch.setattr(lw, "DECISION_LOG", dlog)

    now = time.time()
    # Settled intervals land TODAY: yesterday has none, so no reset claim
    # can be made regardless of today's fills.
    _write(feed, [_settlement(now - 3600 + i * 900) for i in range(2)])
    today = lw.datetime.now(lw.timezone.utc).strftime("%Y-%m-%d")
    _write(dlog, [
        _coin_fill(lw.datetime.now(lw.timezone.utc).strftime("%Y-%m-%d"), "23:45:00"),
        _coin_fill(today, "00:15:00"),
    ])
    # Both fills land today; yesterday has no settled intervals -> no claim.
    state = {"reset_proof_date": None}
    assert lw.reset_proof_check(state) is None


def test_feed_check_flags_staleness(tmp_path, monkeypatch):
    feed = tmp_path / "observations.jsonl"
    monkeypatch.setattr(lw, "FEED", feed)
    _write(feed, [{"ts": time.time() - 10}])
    key, age = lw.feed_check()
    assert key == "" and age < 60
    _write(feed, [{"ts": time.time() - lw.FEED_MAX_AGE_S - 60}])
    key, _ = lw.feed_check()
    assert key == "feed_stale"


def test_pm_feed_check_uses_own_path_and_key(tmp_path, monkeypatch):
    kalshi = tmp_path / "kalshi.jsonl"
    pm = tmp_path / "pm.jsonl"
    monkeypatch.setattr(lw, "FEED", kalshi)
    _write(kalshi, [{"ts": time.time() - 10}])
    _write(pm, [{"ts": time.time() - lw.FEED_MAX_AGE_S - 60}])
    assert lw.feed_check()[0] == ""
    assert lw.feed_check(pm, "pm_feed")[0] == "pm_feed_stale"
    assert lw.feed_check(tmp_path / "missing.jsonl", "pm_feed")[0] == "pm_feed_unreadable"


def test_alerts_target_demo_loop_card_not_ibkr_parent():
    assert lw.ISSUE == "ALG-3411"


def test_reset_missing_fires_when_gated_yesterday_and_silent_today(tmp_path, monkeypatch):
    feed = tmp_path / "observations.jsonl"
    dlog = tmp_path / "decision_log.jsonl"
    monkeypatch.setattr(lw, "FEED", feed)
    monkeypatch.setattr(lw, "DECISION_LOG", dlog)

    utc = lw.timezone.utc
    now = lw.datetime(2026, 3, 10, 2, 0, tzinfo=utc).timestamp()
    yesterday = "2026-03-09"
    today = "2026-03-10"
    # Yesterday: 4 settled intervals, 2 fills -> gated. Today: 3 settled
    # intervals, zero fills -> the reset did not visibly lift.
    _write(feed, [_settlement(now - 86400 + i * 900) for i in range(4)]
           + [_settlement(now - 3600 + i * 900) for i in range(3)])
    _write(dlog, [_coin_fill(yesterday, "01:00:00"), _coin_fill(yesterday, "01:15:00")])

    key, detail = lw.reset_missing_check(now)
    assert key == "envelope_reset_missing"
    assert "did not visibly lift" in detail


def test_reset_missing_quiet_when_fill_present_or_within_grace(tmp_path, monkeypatch):
    feed = tmp_path / "observations.jsonl"
    dlog = tmp_path / "decision_log.jsonl"
    monkeypatch.setattr(lw, "FEED", feed)
    monkeypatch.setattr(lw, "DECISION_LOG", dlog)

    utc = lw.timezone.utc
    now = lw.datetime(2026, 3, 10, 2, 0, tzinfo=utc).timestamp()
    base = [_settlement(now - 86400 + i * 900) for i in range(4)]

    # A: coin filled today -> healthy, no alert.
    _write(feed, base + [_settlement(now - 3600 + i * 900) for i in range(3)])
    _write(dlog, [_coin_fill("2026-03-09", "01:00:00"),
                  _coin_fill("2026-03-10", "00:15:00")])
    assert lw.reset_missing_check(now)[0] is None

    # B: no fills yet but only 1 settled interval today -> too early, no alert.
    _write(feed, base + [_settlement(now - 300)])
    _write(dlog, [_coin_fill("2026-03-09", "01:00:00")])
    assert lw.reset_missing_check(now)[0] is None

    # C: 00:20 UTC, inside the grace window -> no alert even if silent.
    early = lw.datetime(2026, 3, 10, 0, 20, tzinfo=utc).timestamp()
    _write(feed, base + [_settlement(early - 120)])
    assert lw.reset_missing_check(early)[0] is None

    # D: yesterday not gated (fills == intervals) -> nothing expected.
    _write(feed, [_settlement(now - 86400 + i * 900) for i in range(2)])
    _write(dlog, [_coin_fill("2026-03-09", "01:00:00"),
                  _coin_fill("2026-03-09", "01:15:00")])
    assert lw.reset_missing_check(now)[0] is None


def test_workers_check_survives_denied_null_heartbeat(monkeypatch):
    """2026-10-22 incident: denied workers report heartbeat null; the check
    must flag the anomaly, not crash on float(None)."""
    import io
    import urllib.request

    payload = {
        "workers": [
            {"account": "laya", "state": "ready",
             "last_heartbeat": time.time(), "orders_filled": 0},
            {"account": "jev", "state": "denied",
             "last_heartbeat": None, "orders_filled": None},
            {"account": "coin", "state": "denied",
             "last_heartbeat": None, "orders_filled": None},
        ]
    }

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=0):  # noqa: ANN001, ANN202
        return FakeResp(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    key, summary = lw.workers_check()
    assert key.startswith("workers_unhealthy:")
    assert "jev state=denied" in key and "coin state=denied" in key
    assert "heartbeat missing" in key
    assert "hb-none" in summary and "MISMATCH" not in summary


def test_workers_check_ok_when_all_ready(monkeypatch):
    import io
    import urllib.request

    payload = {"workers": [
        {"account": a, "state": "ready", "last_heartbeat": time.time(), "orders_filled": 0}
        for a in ("laya", "jev", "coin")
    ]}

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=0):  # noqa: ANN001, ANN202
        return FakeResp(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    key, summary = lw.workers_check()
    assert key == ""
    assert summary.count("ready") == 3
