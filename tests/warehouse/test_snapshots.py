from concurrent.futures import ThreadPoolExecutor

import pyarrow as pa
import pytest

from algobots.warehouse import Warehouse, WarehouseError


@pytest.fixture
def publish(tmp_path):
    warehouse = Warehouse(tmp_path)
    metadata = dict(
        dataset="recorder",
        provider_release="test-v1",
        query={},
        instrument_mapping={"market": "KXBTC15M.KALSHI"},
        retrieval_start=0,
        retrieval_end=1800,
        timezone="UTC",
        units="USD",
        precision=2,
        adjustment_policy="none",
        schema_version=1,
    )

    def write(snapshot_id="one", times=(0, 900), events=("a", "b")):
        return warehouse.publish(
            snapshot_id,
            pa.table({"timestamp": times, "event": events}),
            instrument_id="KXBTC15M.KALSHI",
            provider="kalshi",
            timestamp_column="timestamp",
            key_columns=["event"],
            expected_interval=900,
            metadata=metadata,
        )

    return warehouse, write


def test_round_trip_and_instrument_discovery(publish):
    warehouse, write = publish
    manifest = write()
    loaded, table = warehouse.load("one")
    assert loaded == manifest
    assert table.num_rows == 2
    assert warehouse.list_snapshots("KXBTC15M.KALSHI") == [manifest]
    assert warehouse.list_snapshots("OTHER") == []
    assert not list((warehouse.root / "_staging").iterdir())


@pytest.mark.parametrize(
    "times,events",
    [
        ((900, 0), ("a", "b")),
        ((0, 1800), ("a", "b")),
        ((0, 900), ("a", "a")),
        ((0, float("nan")), ("a", "b")),
    ],
)
def test_invalid_rows_never_publish(publish, times, events):
    warehouse, write = publish
    with pytest.raises(WarehouseError):
        write(times=times, events=events)
    assert warehouse.list_snapshots("KXBTC15M.KALSHI") == []


def test_concurrent_publish_cannot_replace_snapshot(publish):
    warehouse, write = publish

    def attempt(i):
        try:
            return write(events=(f"a{i}", f"b{i}"))
        except WarehouseError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert warehouse.load("one")[0] == winners[0]


def test_content_mutation_rejected(publish):
    warehouse, write = publish
    manifest = write()
    (warehouse.root / manifest["path"]).write_bytes(b"altered")
    with pytest.raises(WarehouseError, match="hash mismatch"):
        warehouse.load("one")


def test_path_traversal_rejected(publish):
    warehouse, write = publish
    with pytest.raises(WarehouseError, match="identifier"):
        write("../escape")
    with pytest.raises(WarehouseError, match="identifier"):
        warehouse.load("../escape")


def test_snapshot_identity_cannot_be_reused_across_namespaces(publish):
    warehouse, write = publish
    manifest = write()
    with pytest.raises(WarehouseError, match="already published"):
        warehouse.publish(
            "one",
            pa.table({"timestamp": [0, 900], "event": ["a", "b"]}),
            instrument_id="KXBTC15M.KALSHI",
            provider="external",
            timestamp_column="timestamp",
            key_columns=["event"],
            expected_interval=900,
            namespace="external",
            metadata=manifest,
        )
    assert warehouse.load("one")[0] == manifest
