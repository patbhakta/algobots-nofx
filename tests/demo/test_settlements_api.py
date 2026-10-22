"""ALG-3357: /demo/api/settlements serves Kalshi ground-truth settle marks."""

import json

from algobots.api.config import get_settings


def _rows():
    return [
        # settled: mark above strike -> YES
        {"event": "KXBTC15M-26OCT221200", "strike": 100.0, "outcome": 1,
         "ts": 1792680000.0, "p": 0.5, "conf": 0.0, "settle_value": "101.5",
         "settled_ts": 1792680030.0, "mkt_mid": 0.55},
        # settled: mark below strike -> NO
        {"event": "KXBTC15M-26OCT221215", "strike": 100.0, "outcome": 0,
         "ts": 1792680900.0, "p": 0.5, "conf": 0.0, "settle_value": "99.5",
         "settled_ts": 1792680930.0, "mkt_mid": 0.45},
        # still open: must be omitted
        {"event": "KXBTC15M-26OCT221230", "strike": 100.0, "outcome": None,
         "ts": 1792681800.0, "p": 0.5, "conf": 0.0},
        # malformed junk line: must be skipped
        "not json at all",
    ]


def test_settlements_serves_settled_only(client, tmp_path, monkeypatch):
    feed = tmp_path / "feed.jsonl"
    feed.write_text("\n".join(json.dumps(r) if isinstance(r, dict) else r for r in _rows()))
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(feed))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    get_settings.cache_clear()

    r = client.get("/demo/api/settlements")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    events = [s["event"] for s in body["settlements"]]
    assert events == ["KXBTC15M-26OCT221215", "KXBTC15M-26OCT221200"]  # newest first
    newest = body["settlements"][0]
    assert newest["outcome"] == 0 and newest["settle_value"] == "99.5"
    assert all("outcome" in s and s["outcome"] in (0, 1) for s in body["settlements"])


def test_settlements_limit_and_missing_feed(client, tmp_path, monkeypatch):
    feed = tmp_path / "feed.jsonl"
    rows = []
    for i in range(5):
        rows.append(json.dumps({"event": f"E{i}", "strike": 1.0, "outcome": 1,
                                "ts": float(i), "p": 0.5, "conf": 0,
                                "settle_value": "2", "settled_ts": float(i)}))
    feed.write_text("\n".join(rows))
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(feed))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    get_settings.cache_clear()

    r = client.get("/demo/api/settlements", params={"limit": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 5  # total settled
    assert len(body["settlements"]) == 2
    assert body["settlements"][0]["event"] == "E4"  # newest kept

    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(tmp_path / "nope.jsonl"))
    get_settings.cache_clear()
    r = client.get("/demo/api/settlements")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "settlements": []}
