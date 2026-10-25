import json
from concurrent.futures import ThreadPoolExecutor

import pyarrow as pa
import pytest

from algobots.strategies import backtest, quantlab
from algobots.strategies.studio import StudioError, compile_studio_strategy, parse_draft
from algobots.warehouse import Warehouse

DRAFT = {
    "schema_version": 1,
    "name": "OpenBB SPY daily",
    "universe": {"asset_class": "equity", "symbols": ["SPY.NYSE"], "datafeed": "sim"},
    "signals": {
        "cadence": "1d",
        "bars": 2,
        "entry": {"left": {"source": "close"}, "op": "gt", "right": {"value": 0}},
        "exit": {"left": {"source": "close"}, "op": "lt", "right": {"value": 0}},
    },
    "decision": {"mode": "deterministic"},
    "risk": {"max_order_value": "1000", "max_daily_loss": "100", "max_positions": 1},
}


@pytest.fixture
def snapshot(tmp_path):
    rows = [
        dict(
            timestamp=86400 * (i + 1),
            open=100 + i,
            high=102 + i,
            low=99 + i,
            close=101 + i,
            volume=1000,
        )
        for i in range(5)
    ]
    metadata = dict(
        dataset="openbb-spy-daily",
        provider_release="fixture",
        query={},
        instrument_mapping={"SPY": "SPY.NYSE"},
        retrieval_start=0,
        retrieval_end=500000,
        timezone="UTC",
        units="USD,shares",
        precision=2,
        adjustment_policy="none",
        schema_version=1,
        catalog_data_class="Bar",
        gap_policy="irregular-recorded-events",
    )
    manifest = Warehouse(tmp_path).publish(
        "openbb-test",
        pa.Table.from_pylist(rows),
        instrument_id="SPY.NYSE",
        provider="yfinance",
        timestamp_column="timestamp",
        key_columns=["timestamp"],
        expected_interval=None,
        metadata=metadata,
        namespace="external",
    )
    return tmp_path, manifest


def test_ohlc_snapshot_keeps_rows_hash_and_instrument(snapshot):
    root, manifest = snapshot
    dataset = backtest.load_warehouse("openbb-test", root, "SPY.NYSE")
    assert dataset.sha256 == manifest["sha256"]
    assert len(dataset.rows) == 5 and dataset.describe()["instrument_id"] == "SPY.NYSE"
    with pytest.raises(StudioError, match="instrument"):
        backtest.load_warehouse("openbb-test", root, "KXBTC15M.KALSHI")
    dataset.path.write_bytes(b"corrupt")
    with pytest.raises(StudioError, match="hash"):
        backtest.load_warehouse("openbb-test", root, "SPY.NYSE")


def test_http_backtest_dispatches_and_publishes_immutable_evidence(
    client, founder_headers, snapshot, monkeypatch, tmp_path
):
    from algobots.api.config import get_settings

    root, manifest = snapshot
    monkeypatch.setenv("ALGOBOTS_WAREHOUSE_ROOT", str(root))
    monkeypatch.setenv("ALGOBOTS_EVIDENCE_NOTEBOOK_ROOT", str(tmp_path / "notebooks"))
    get_settings.cache_clear()
    calls = []

    def execute(queue, artifact, identity, digest):
        calls.append((identity, digest, artifact["implementation"]))
        return dict(
            executor="NautilusTrader BacktestEngine 2.0.0rc6",
            engine={},
            implementation="condition_dsl.v1",
            params={},
            risk_envelope={},
            metrics={"pnl": "0.00"},
            equity_curve=[],
            trades=[],
        )

    monkeypatch.setattr(quantlab, "dispatch", execute)
    try:
        created = client.post("/api/studio/strategies", json=DRAFT, headers=founder_headers)
        assert created.status_code == 201
        url = f"/api/studio/strategies/{created.json()['id']}"
        assert client.post(url + "/compile", headers=founder_headers).status_code == 201
        first = client.post(
            url + "/backtest", json={"snapshot_id": "openbb-test"}, headers=founder_headers
        )
        assert first.status_code == 201, first.text
        second = client.post(
            url + "/backtest", json={"snapshot_id": "openbb-test"}, headers=founder_headers
        )
        assert second.json()["id"] == first.json()["id"]
        assert calls == [("openbb-test", manifest["sha256"], "condition_dsl.v1")]
        assert list((tmp_path / "notebooks" / "evidence").glob("*.py"))
    finally:
        get_settings.cache_clear()


def test_quantlab_response_identity_is_verified_and_queue_cleaned(tmp_path, monkeypatch):
    artifact = compile_studio_strategy(parse_draft(DRAFT)).model_dump(mode="json")

    def respond(_):
        request = next(tmp_path.glob("*.request.json"))
        reply = request.with_name(request.name.replace(".request.json", ".result.json"))
        reply.write_text(json.dumps(dict(snapshot_id="wrong", sha256="bad", result={})))

    monkeypatch.setattr(quantlab.time, "sleep", respond)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(quantlab.dispatch, tmp_path, artifact, "openbb-test", "expected")
        with pytest.raises(ValueError, match="identity mismatch"):
            future.result(timeout=5)
    assert not list(tmp_path.iterdir())
