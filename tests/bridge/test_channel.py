"""ALG-3340 file-channel contract tests: intents in, OrderFilled out.

The channel is plain files by design (both containers and the control plane
see the same directory); these tests pin the lifecycle: atomic claim,
at-least-once crash replay, idempotent outcomes, fills JSONL.
"""

from __future__ import annotations

import json

from algobots.bridge import channel as CH


def _intent(tmp_path, n=1, account="laya", **over):
    base = {
        "intent_id": f"it-test-{n:04d}",
        "account": account,
        "symbol": "KXBTC15M-26OCT131230-YES",
        "side": "buy",
        "qty": 10,
        "status": "admitted",
    }
    base.update(over)
    CH.write_intent(tmp_path, base)
    return base


def test_write_then_claim_once(tmp_path):
    _intent(tmp_path, 1)
    claimed, malformed = CH.claim_intents(tmp_path, "laya")
    assert [c["intent_id"] for c in claimed] == ["it-test-0001"] and not malformed
    CH.finish_intent(tmp_path, "laya", "it-test-0001", {"status": "filled"})
    assert CH.claim_intents(tmp_path, "laya") == ([], [])  # finished: never again
    assert not list((tmp_path / "intents").glob("*.json"))


def test_claims_are_account_scoped(tmp_path):
    _intent(tmp_path, 1, account="laya")
    _intent(tmp_path, 2, account="jev")
    claimed, _ = CH.claim_intents(tmp_path, "laya")
    assert [c["account"] for c in claimed] == ["laya"]
    assert (tmp_path / "intents" / "it-test-0002.json").exists()  # jev's, untouched


def test_crash_leftover_replays_at_least_once(tmp_path):
    it = _intent(tmp_path, 1)
    CH.claim_intents(tmp_path, "laya")  # claimed, "crash" before finish
    claimed, _ = CH.claim_intents(tmp_path, "laya")
    assert [c["intent_id"] for c in claimed] == [it["intent_id"]]  # replayed


def test_malformed_and_headless_files_never_replay(tmp_path):
    (tmp_path / "intents").mkdir(parents=True)
    (tmp_path / "intents" / "bad.json").write_text("{not json")
    (tmp_path / "intents" / "headless.json").write_text(json.dumps({"account": "laya", "qty": 1}))
    claimed, malformed = CH.claim_intents(tmp_path, "laya")
    assert claimed == [] and len(malformed) == 1
    CH.reject_malformed(tmp_path, malformed[0], "intent file is not a JSON object")
    assert CH.claim_intents(tmp_path, "laya") == ([], [])  # rejected once, gone
    done = json.loads((tmp_path / "done" / "bad.json").read_text())
    assert done["status"] == "rejected"
    headless = json.loads((tmp_path / "done" / "headless.json").read_text())  # no intent_id
    assert "qty" in headless  # moved verbatim, never replayed


def test_finish_intent_is_idempotent_and_carries_outcome(tmp_path):
    it = _intent(tmp_path, 7)
    CH.claim_intents(tmp_path, "laya")
    CH.finish_intent(
        tmp_path, "laya", it["intent_id"], {"status": "filled", "fill": {"px": "0.50"}}
    )
    CH.finish_intent(tmp_path, "laya", it["intent_id"], {"status": "filled"})  # replay: no-op
    done = json.loads((tmp_path / "done" / "it-test-0007.json").read_text())
    assert done["status"] == "filled" and done["qty"] == 10 and done["side"] == "buy"
    assert not list((tmp_path / "processing" / "laya").glob("*.json"))


def test_fills_jsonl_roundtrip_and_limit(tmp_path):
    for n in range(4):
        CH.append_fill(tmp_path, "laya", {"intent_id": f"i{n}", "px": "0.50"})
    rows = CH.read_fills(tmp_path, "laya")
    assert [r["intent_id"] for r in rows] == ["i0", "i1", "i2", "i3"]
    assert [r["intent_id"] for r in CH.read_fills(tmp_path, "laya", limit=2)] == ["i2", "i3"]
    assert CH.read_fills(tmp_path, "jev") == []


def test_find_intent_across_states(tmp_path):
    it = _intent(tmp_path, 3)
    assert CH.find_intent(tmp_path, it["intent_id"])[0] == "admitted"
    CH.claim_intents(tmp_path, "laya")
    assert CH.find_intent(tmp_path, it["intent_id"])[0] == "processing"
    CH.finish_intent(tmp_path, "laya", it["intent_id"], {"status": "filled"})
    state, payload = CH.find_intent(tmp_path, it["intent_id"])
    assert state == "done" and payload["status"] == "filled"
    assert CH.find_intent(tmp_path, "it-nope") is None


def test_channel_stats_counts_states_and_fills(tmp_path):
    _intent(tmp_path, 1)
    _intent(tmp_path, 2)
    CH.claim_intents(tmp_path, "laya")  # both claimed
    CH.finish_intent(tmp_path, "laya", "it-test-0001", {"status": "filled"})
    CH.append_fill(tmp_path, "laya", {"ts_utc": "2026-10-13T17:15:00.000Z"})
    stats = CH.channel_stats(tmp_path)
    assert stats["intents_admitted"] == 0
    assert stats["intents_processing"] == 1  # the unfinished claim
    assert stats["intents_done"] == 1
    assert stats["fills_recorded"] == 1
    assert stats["last_fill_ts"] == "2026-10-13T17:15:00.000Z"


def test_symbol_shape():
    assert CH.valid_symbol("KXBTC15M-26OCT131230-YES")
    assert CH.valid_symbol("X-no")
    assert not CH.valid_symbol("NOEVENT")
    assert not CH.valid_symbol("-YES")
    assert not CH.valid_symbol("")


def test_now_id_is_sortable_and_unique():
    a, b = CH.now_id(1760000000.0), CH.now_id(1760000000.001)
    assert a < b and a != b and a.startswith("it-2025")
