"""ALG-3418: Studio backtests on a frozen KXBTC15M recorder dataset.

The fixture is a deterministic 48-interval recorder feed: a BTC close chain
with trending stretches (so mom3x15m/vol20 leaves the abstain band), strikes
set to the previous close as on KXBTC15M, and a recorded book on two thirds
of the rows. Every number below comes from the real Nautilus BacktestEngine.
"""

import copy
import json
import math
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from algobots.api.config import get_settings
from algobots.strategies import backtest as bt
from algobots.strategies.studio import StudioError, compile_studio_strategy, parse_draft
from tests.conftest import TEST_PASSWORD
from tests.strategies.test_studio import DRAFT, NOFX_MOMENTUM

pytest.importorskip("nautilus_trader")

T0 = 1_792_656_000  # 2026-10-22 08:00 UTC, an interval boundary


def recorder_rows(n: int = 48) -> list[dict]:
    rows, prev = [], 80_000.0
    for i in range(n):
        settle = round(prev + 90 * math.sin(i / 5) + 30 * ((i * 7) % 5 - 2), 2)
        open_ts = T0 + i * 900
        book = i % 3 != 0
        rows.append(
            {
                "event": f"KXBTC15M-SYN{i:03d}",
                "market": f"KXBTC15M-SYN{i:03d}-00",
                "strike": prev,
                "outcome": int(settle > prev),
                "ts": open_ts + 20.0,
                "p": 0.5,
                "conf": 0.0,
                "p_source": "none",
                "open_ts": float(open_ts),
                "close_ts": float(open_ts + 900),
                "mkt_yes_bid": 0.47 if book else None,
                "mkt_yes_ask": 0.49 if book else None,
                "mkt_mid": 0.48 if book else None,
                "settled_ts": open_ts + 920.0,
                "settle_value": f"{settle:.2f}",
            }
        )
        prev = settle
    return rows


def write_feed(path, rows, pending: bool = True) -> None:
    lines = [json.dumps(r) for r in rows]
    if pending:  # the live interval: decided, not settled — never in a dataset
        lines.append(json.dumps({**rows[-1], "event": "KXBTC15M-PENDING", "outcome": None}))
    lines.append("not json")
    path.write_text("\n".join(lines) + "\n")


def momentum_artifact(min_edge: float = 0.05) -> dict:
    draft = {
        **DRAFT,
        "name": "Kalshi momentum",
        "universe": {
            "asset_class": "prediction",
            "symbols": ["KXBTC15M.KALSHI"],
            "datafeed": "kalshi",
        },
        "signals": {"cadence": "15m", "bars": 20},
        "decision": {"mode": "deterministic", "min_confidence": min_edge},
        "risk": {"max_positions": 1, "max_order_value": "5.00", "max_daily_loss": "20.00"},
    }
    return compile_studio_strategy(parse_draft(draft)).model_dump(mode="json")


@pytest.fixture()
def frozen(tmp_path):
    feed = tmp_path / "observations.jsonl"
    write_feed(feed, recorder_rows())
    return bt.freeze(feed, tmp_path / "state")


def test_freeze_is_content_addressed_and_write_once(tmp_path, frozen):
    assert frozen.id == f"{bt.DATASET_SOURCE}@{frozen.sha256[:12]}"
    assert len(frozen.rows) == 48  # pending + malformed lines excluded
    assert frozen.path.name == f"{frozen.sha256}.jsonl"
    d = frozen.describe()
    assert d["first_event"] == "KXBTC15M-SYN000" and d["last_event"] == "KXBTC15M-SYN047"
    assert d["start"] == "2026-10-22T08:00:00+00:00" and d["end"] == "2026-10-22T20:00:00+00:00"
    assert (
        d["name"]
        == "KXBTC15M recorder 2026-10-22 08:00 to 2026-10-22 20:00 UTC (48 settled intervals)"
    )

    # same settled rows (any order, any pending tail) -> same dataset
    feed2 = tmp_path / "shuffled.jsonl"
    write_feed(feed2, list(reversed(recorder_rows())), pending=False)
    assert bt.freeze(feed2, tmp_path / "state").sha256 == frozen.sha256

    # one more settled interval -> a new snapshot; the old one is untouched
    write_feed(feed2, recorder_rows(49))
    grown = bt.freeze(feed2, tmp_path / "state")
    assert grown.sha256 != frozen.sha256
    assert bt.load(frozen.id, tmp_path / "state").rows == frozen.rows


def test_load_fails_closed(tmp_path, frozen):
    state = tmp_path / "state"
    for bad in (
        "other@" + frozen.sha256[:12],
        f"{bt.DATASET_SOURCE}@nothex",
        f"{bt.DATASET_SOURCE}@000000000000",
    ):
        with pytest.raises(StudioError) as e:
            bt.load(bad, state)
        assert e.value.field == "dataset_id"
    frozen.path.write_text(frozen.path.read_text().replace('"outcome":0', '"outcome":1', 1))
    with pytest.raises(StudioError, match="content-hash"):
        bt.load(frozen.id, state)
    with pytest.raises(StudioError) as e:
        bt.freeze(tmp_path / "missing.jsonl", state)
    assert e.value.field == "dataset"


def test_backtest_is_deterministic_on_nautilus(frozen):
    art = momentum_artifact()
    a, b = bt.run_backtest(art, frozen), bt.run_backtest(art, frozen)
    assert a == b
    assert a["executor"].startswith("NautilusTrader ") and "BacktestEngine" in a["executor"]
    m = a["metrics"]
    assert m["intervals"] == 48 and len(a["equity_curve"]) == 48
    # 12 contiguous closes before the first signal; the rest are scored
    assert m["scored"] == 36
    assert m["filled"] + m["abstain"] + m["blocked"] == 48
    assert m["filled"] == len(a["trades"]) > 0
    assert sum(m["px_sources"].values()) == m["filled"]
    assert sum(m["blocked_by"].values()) == m["blocked"]
    # every entry respects the artifact's max_order_value (5.00 USD)
    assert all(int(t["qty"]) * float(t["price"]) <= 5.0 for t in a["trades"])
    # P&L is the engine's: ending equity - capital, and the curve ends there
    assert Decimal(m["pnl"]) == Decimal(m["ending_equity"]) - 100
    assert a["equity_curve"][-1]["equity"] == m["ending_equity"]
    assert 0 <= m["hit_rate"] <= 1 and 0 <= m["brier"] <= 1
    # pinned so a behaviour change is loud
    assert (m["filled"], m["wins"], m["pnl"], m["fees"]) == PINNED


PINNED = (35, 30, "113.50", "6.10")


def test_no_look_ahead(frozen):
    """Flipping a later outcome never changes an earlier decision."""
    art = momentum_artifact()
    base = bt.run_backtest(art, frozen)
    rows = copy.deepcopy(frozen.rows)
    rows[-1]["outcome"] ^= 1
    rows[-1]["settle_value"] = "1.00"
    altered = bt.BacktestDataset(frozen.id, "x", rows, frozen.path)
    other = bt.run_backtest(art, altered)
    assert base["trades"][:-1] == other["trades"][: len(base["trades"]) - 1]
    assert [t["side"] for t in base["trades"]] == [t["side"] for t in other["trades"]]


def test_dsl_artifact_is_refused_with_owning_field(frozen):
    art = compile_studio_strategy(parse_draft(DRAFT)).model_dump(mode="json")
    with pytest.raises(StudioError) as e:
        bt.run_backtest(art, frozen)
    assert e.value.field == "signals.entry"


# --- API contract ------------------------------------------------------------


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def token(client: TestClient, founder: dict) -> str:
    r = client.post("/api/nofx/login", json={"email": founder["email"], "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def recorder(tmp_path, monkeypatch):
    feed = tmp_path / "observations.jsonl"
    write_feed(feed, recorder_rows())
    from algobots.warehouse import Warehouse
    from algobots.warehouse.recorders import export_rows

    warehouse = Warehouse(tmp_path / "warehouse")
    export_rows(
        warehouse,
        "kalshi",
        recorder_rows(),
        "recorder-48",
        instrument_id="KXBTC15M.KALSHI",
        provider_release="fixture",
        retrieved_at=T0,
        query={},
        timestamp_column="close_ts",
        key_columns=["event"],
    )
    monkeypatch.setenv("ALGOBOTS_WAREHOUSE_ROOT", str(warehouse.root))
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(feed))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path / "state"))
    # Evidence publication must target a test-local root: the production
    # default is the FunnyTree mount, which only exists on the deployment
    # host (CI runners cannot mkdir under /mnt, surfacing as 503s).
    monkeypatch.setenv("ALGOBOTS_EVIDENCE_NOTEBOOK_ROOT", str(tmp_path / "evidence-root"))
    monkeypatch.setenv("ALGOBOTS_EVIDENCE_BASE_URL", "http://evidence.test")
    get_settings.cache_clear()
    yield feed
    get_settings.cache_clear()


def test_backtest_route_contract(client, token, recorder):
    r = client.post(
        "/api/nofx/strategies",
        json={"name": "Kalshi momentum", "config": NOFX_MOMENTUM},
        headers=_h(token),
    )
    studio = r.json()["studio"]
    url = f"/api/studio/strategies/{studio['draft_id']}"

    assert client.post(f"{url}/backtest").status_code == 401
    assert client.get(f"{url}/backtests", headers=_h(token)).json() == {"backtests": []}

    r1 = client.post(f"{url}/backtest", headers=_h(token))
    assert r1.status_code == 201, r1.text
    res = r1.json()
    assert res["artifact"]["artifact_hash"] == studio["artifact_hash"]
    assert res["artifact"]["implementation"] == "kalshi_momentum.v1"
    ds = res["dataset"]
    assert ds["source"] == "warehouse" and ds["rows"] == 48
    assert ds["id"] == "recorder-48"
    assert res["executor"].startswith("NautilusTrader ")
    for key in ("pnl", "hit_rate", "brier", "ending_equity", "max_drawdown"):
        assert key in res["metrics"]
    assert len(res["equity_curve"]) == 48
    assert (
        client.patch(
            f"/api/strategies/{res['id']}", json={"params": {}}, headers=_h(token)
        ).status_code
        == 409
    )
    assert client.delete(f"/api/strategies/{res['id']}", headers=_h(token)).status_code == 409

    discovery = client.get(
        "/api/studio/snapshots", params={"instrument_id": "KXBTC15M.KALSHI"}, headers=_h(token)
    )
    assert discovery.status_code == 200
    by_draft = client.get(f"{url}/snapshots", headers=_h(token))
    assert by_draft.status_code == 200 and by_draft.json() == discovery.json()
    assert discovery.json()["snapshots"][0]["snapshot_id"] == "recorder-48"
    assert (
        client.get("/api/studio/snapshots", params={"instrument_id": "KXBTC15M.KALSHI"}).status_code
        == 401
    )

    # same artifact + same dataset -> the stored row, not a re-run
    r2 = client.post(f"{url}/backtest", headers=_h(token))
    assert r2.status_code == 200 and r2.json()["id"] == res["id"]

    # Growing the live feed does not mutate warehouse input or its cached result.
    write_feed(recorder, recorder_rows(51))
    unchanged = client.post(f"{url}/backtest", headers=_h(token))
    assert unchanged.status_code == 200 and unchanged.json()["id"] == res["id"]
    from algobots.warehouse import Warehouse
    from algobots.warehouse.recorders import export_rows

    export_rows(
        Warehouse(recorder.parent / "warehouse"),
        "kalshi",
        recorder_rows(51),
        "recorder-51",
        instrument_id="KXBTC15M.KALSHI",
        provider_release="fixture",
        retrieved_at=T0,
        query={},
        timestamp_column="close_ts",
        key_columns=["event"],
    )
    r3 = client.post(f"{url}/backtest", headers=_h(token))
    assert r3.status_code == 201 and r3.json()["dataset"]["rows"] == 51
    r4 = client.post(f"{url}/backtest", json={"dataset_id": ds["id"]}, headers=_h(token))
    assert r4.status_code == 200 and r4.json()["id"] == res["id"]
    bad = client.post(f"{url}/backtest", json={"dataset_id": "nope@0"}, headers=_h(token))
    assert bad.status_code == 422 and bad.json()["detail"]["field"] == "dataset_id"

    listed = client.get(f"{url}/backtests", headers=_h(token)).json()["backtests"]
    assert [b["id"] for b in listed] == [r3.json()["id"], res["id"]]


def test_backtest_needs_a_compiled_backtestable_artifact(client, token, recorder):
    r = client.post("/api/studio/strategies", json=DRAFT, headers=_h(token))
    url = f"/api/studio/strategies/{r.json()['id']}"
    assert client.post(f"{url}/backtest", headers=_h(token)).status_code == 409
    client.post(f"{url}/compile", headers=_h(token))
    dsl = client.post(f"{url}/backtest", headers=_h(token))
    assert dsl.status_code == 422 and dsl.json()["detail"]["field"] == "dataset_id"
    assert (
        client.post("/api/studio/strategies/not-a-uuid/backtest", headers=_h(token)).status_code
        == 404
    )


def test_concurrent_backtests_across_drafts_share_one_immutable_row(
    client, token, recorder, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    urls = []
    for name in ("same-config-a", "same-config-b"):
        response = client.post(
            "/api/nofx/strategies",
            json={"name": name, "config": NOFX_MOMENTUM},
            headers=_h(token),
        )
        urls.append(f"/api/studio/strategies/{response.json()['studio']['draft_id']}/backtest")
    # Names are part of the artifact. Make two drafts with exactly the same config.
    response = client.post(
        "/api/nofx/strategies",
        json={"name": "same-config-a", "config": NOFX_MOMENTUM},
        headers=_h(token),
    )
    urls[1] = f"/api/studio/strategies/{response.json()['studio']['draft_id']}/backtest"
    barrier = Barrier(2)

    def run(artifact, dataset):
        barrier.wait(timeout=10)
        return {"metrics": {"pnl": "0.00"}, "fixture": True}

    monkeypatch.setattr(bt, "run_backtest", run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda url: client.post(
                    url, json={"snapshot_id": "recorder-48"}, headers=_h(token)
                ),
                urls,
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json() == responses[1].json()
