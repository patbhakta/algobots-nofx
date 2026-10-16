"""ALG-3381: the coinflip share-out keeps observations and payoff models apart."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from algobots.shareout import coinflip

DATA = Path(__file__).resolve().parents[2] / "data/research/laya-kalshi"


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "coinflip.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_preserved_archive_numbers():
    rows = coinflip.load_rows(DATA / "coinflip.jsonl")
    s = coinflip.summarise(rows)
    assert (s.n, s.hits) == (56, 28)
    assert s.ends["even"] == pytest.approx(0.0)
    # The Oct 14 draft's -$2.52 is reproduced as Model B, not substituted.
    assert s.ends["fee"] == pytest.approx(28 * 0.91 - 28 * 1.00) == pytest.approx(-2.52)
    assert s.p_value == pytest.approx(1.0)
    assert coinflip.FEE_9PCT.breakeven == pytest.approx(1 / 1.91)


def test_report_never_presents_a_recorded_dollar_figure(tmp_path):
    hashes = coinflip.build(DATA / "coinflip.jsonl", DATA / "coinflip_markets.json", tmp_path)
    page = (tmp_path / "coinflip.html").read_text()
    assert page.count("<td class=na>not recorded</td>") == 56
    # The old placeholder appears once, quoted in the correction note, never as data.
    assert page.count("$+0.00") == 1 and "Correction to the previous version" in page
    assert "<b>none</b><span>recorded P&amp;L</span>" in page
    assert "<svg" in page and "Model A" in page and "Model B" in page
    assert "−$2.52" in page and "28 × $0.91 − 28 × $1.00" in page
    assert not re.search(r"<(script|link|img)\b", page)  # standalone, no external assets
    index = (tmp_path / "index.html").read_text()
    assert 'href="coinflip.html"' in index
    assert "56 settled predictions · 28 hits (50.0%)" in index
    # Deterministic: a rebuild is byte-identical.
    assert (
        coinflip.build(DATA / "coinflip.jsonl", DATA / "coinflip_markets.json", tmp_path / "again")
        == hashes
    )


def test_hit_flag_must_match_pick_rule(tmp_path):
    bad = _write(
        tmp_path,
        [{"event": "KXBTC15M-26SEP181245", "p": 0.7, "outcome": 0, "hit": True, "ts": 1.0}],
    )
    with pytest.raises(ValueError, match="hit flag"):
        coinflip.load_rows(bad)


def test_money_fields_fail_closed(tmp_path):
    rows = _write(
        tmp_path,
        [
            {
                "event": "KXBTC15M-26SEP181245",
                "p": 0.3,
                "outcome": 0,
                "hit": True,
                "ts": 1.0,
                "pnl": 0.4,
            }
        ],
    )
    with pytest.raises(ValueError, match="money fields"):
        coinflip.load_rows(rows)


def test_market_result_must_agree(tmp_path):
    rows = coinflip.load_rows(
        _write(
            tmp_path,
            [{"event": "KXBTC15M-26SEP181245", "p": 0.3, "outcome": 0, "hit": True, "ts": 1.0}],
        )
    )
    markets = tmp_path / "m.json"
    markets.write_text(json.dumps([{"event": "KXBTC15M-26SEP181245", "result": "yes"}]))
    with pytest.raises(ValueError, match="disagrees"):
        coinflip.load_markets(markets, rows)


def test_close_time_and_streaks():
    assert coinflip.close_time("KXBTC15M-26SEP181245") == "Sep 18 12:45 ET"
    rows = [coinflip.Row(f"E{i}", 0.7, h, bool(h), 0.0) for i, h in enumerate([1, 1, 0, 0, 0, 1])]
    assert coinflip.streaks(rows) == {True: (2, 0), False: (3, 2)}
