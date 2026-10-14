import json
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from algobots.research.massive_datafeed import fetch_aggregates


def test_fetches_normalizes_and_then_uses_funnytree_cache(tmp_path):
    calls = []

    def transport(url, headers):
        calls.append((url, headers))
        return {
            "status": "OK",
            "results": [
                {
                    "t": 1_700_000_000_000,
                    "o": 10,
                    "h": 12,
                    "l": 9,
                    "c": 11,
                    "v": 42,
                    "n": 7,
                    "vw": 10.5,
                }
            ],
        }

    kwargs = {
        "ticker": "aapl",
        "start": date(2026, 10, 1),
        "end": date(2026, 10, 2),
        "cache_root": tmp_path,
        "api_key": "secret-value",
        "transport": transport,
    }
    first = fetch_aggregates(**kwargs)
    second = fetch_aggregates(**kwargs)

    assert first["cache"] == "miss"
    assert second["cache"] == "hit"
    assert len(calls) == 1
    url, headers = calls[0]
    assert urlparse(url).path.endswith("/AAPL/range/1/day/2026-10-01/2026-10-02")
    assert parse_qs(urlparse(url).query)["limit"] == ["50000"]
    assert headers == {"Authorization": "Bearer secret-value"}
    assert first["bars"][0]["close"] == 11.0
    cache_text = next(tmp_path.rglob("*.json")).read_text()
    assert "secret-value" not in cache_text
    assert json.loads(cache_text)["purpose"].startswith("research-only")


def test_cache_hit_needs_no_api_key(tmp_path):
    target = tmp_path / "MSFT" / "day" / "1-2026-10-01-2026-10-02.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"bars": [{"close": 1}]}))

    result = fetch_aggregates(
        "MSFT", date(2026, 10, 1), date(2026, 10, 2), cache_root=tmp_path
    )

    assert result == {"bars": [{"close": 1}], "cache": "hit"}


@pytest.mark.parametrize("ticker", ["", "AAPL/../KEY", "X:BTCUSD", "TOO-LONG-SYMBOL-NAME"])
def test_rejects_non_equity_or_unsafe_ticker(ticker, tmp_path):
    with pytest.raises(ValueError):
        fetch_aggregates(
            ticker,
            date(2026, 10, 1),
            date(2026, 10, 2),
            cache_root=tmp_path,
            api_key="unused",
        )


def test_missing_key_fails_closed_without_transport(tmp_path, monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MASSIVE_API_KEY"):
        fetch_aggregates("AAPL", date(2026, 10, 1), date(2026, 10, 2), cache_root=tmp_path)
