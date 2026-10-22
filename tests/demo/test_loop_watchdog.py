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
