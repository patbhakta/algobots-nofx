"""Immutable, validated Parquet snapshots shared by recorder and consumers.

The manifest is the publication marker. Readers never discover staged data.
Publication uses hard links (atomic and no-clobber), not overwriting renames.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


class WarehouseError(ValueError):
    """Invalid, missing, conflicting, or corrupted warehouse snapshot."""


def _token(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise WarehouseError(f"invalid warehouse identifier: {value!r}")
    return value


def _digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class Warehouse:
    def __init__(self, root: Path):
        self.root = Path(root)

    def publish(
        self,
        snapshot_id: str,
        table: pa.Table,
        *,
        instrument_id: str,
        provider: str,
        timestamp_column: str,
        key_columns: list[str],
        expected_interval: float | None,
        metadata: dict[str, Any],
        namespace: str = "ledger",
    ) -> dict[str, Any]:
        """Validate recorder rows and publish a new snapshot without replacement.

        Timestamps and expected_interval use seconds since Unix epoch. Required
        provenance is explicit; missing information must be supplied by exporters.
        """
        _token(snapshot_id)
        if namespace not in {"ledger", "external"}:
            raise WarehouseError("unknown warehouse namespace")
        _token(provider)
        dataset = _token(str(metadata.get("dataset", "")))
        schema = _token(str(metadata.get("schema_version", "")))
        required = {
            "dataset",
            "provider_release",
            "query",
            "instrument_mapping",
            "retrieval_start",
            "retrieval_end",
            "timezone",
            "units",
            "precision",
            "adjustment_policy",
            "schema_version",
        }
        if required - metadata.keys():
            raise WarehouseError(f"missing provenance: {sorted(required - metadata.keys())}")
        if metadata["timezone"] != "UTC":
            raise WarehouseError("event timestamps must use UTC")
        if not instrument_id or not provider or not key_columns or table.num_rows == 0:
            raise WarehouseError("instrument, provider, keys, and nonempty rows required")
        if expected_interval is None:
            if metadata.get("gap_policy") != "irregular-recorded-events":
                raise WarehouseError("irregular data requires explicit gap policy")
        elif not math.isfinite(expected_interval) or expected_interval <= 0:
            raise WarehouseError("expected_interval must be finite and positive")
        if not {timestamp_column, *key_columns} <= set(table.column_names):
            raise WarehouseError("timestamp/key columns missing")
        rows = table.select(list(dict.fromkeys([timestamp_column, *key_columns]))).to_pylist()
        try:
            times = [float(row[timestamp_column]) for row in rows]
            keys = [tuple(row[column] for column in key_columns) for row in rows]
            if any(not math.isfinite(t) for t in times):
                raise WarehouseError("timestamps must be finite")
            if any(any(value is None for value in key) for key in keys):
                raise WarehouseError("null key")
            if len(set(keys)) != len(keys):
                raise WarehouseError("duplicate event key")
            deltas = [b - a for a, b in zip(times, times[1:], strict=False)]
            if any(delta <= 0 for delta in deltas):
                raise WarehouseError("timestamps must be strictly ordered")
            if expected_interval is not None and any(
                not math.isclose(delta, expected_interval, abs_tol=1e-6) for delta in deltas
            ):
                raise WarehouseError("event-time gap or unexpected cadence")
        except (TypeError, KeyError) as exc:
            raise WarehouseError("invalid timestamp or event key") from exc
        staging = self.root / "_staging"
        staging.mkdir(parents=True, exist_ok=True)
        stage = staging / uuid.uuid4().hex
        stage.mkdir(mode=0o770)
        try:
            parquet = stage / "data.parquet"
            pq.write_table(table, parquet)
            content_hash = _digest(parquet.read_bytes())
            date = datetime.fromtimestamp(times[0], UTC).date().isoformat()
            data_path = (
                f"ledger/{provider}/v{schema}/date={date}/part-{content_hash}.parquet"
                if namespace == "ledger"
                else f"external/{provider}/{dataset}/v{schema}/snapshot={snapshot_id}/"
                f"part-{content_hash}.parquet"
            )
            manifest = {
                **metadata,
                "snapshot_id": snapshot_id,
                "namespace": namespace,
                "instrument_id": instrument_id,
                "provider": provider,
                "timestamp_column": timestamp_column,
                "key_columns": key_columns,
                "expected_interval": expected_interval,
                "event_start": times[0],
                "event_end": times[-1],
                "row_count": table.num_rows,
                "sha256": content_hash,
                "path": data_path,
            }
            manifests = self.root / "manifests" / namespace / dataset
            manifests.mkdir(parents=True, exist_ok=True)
            target = self.root / data_path
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.hardlink_to(parquet)
            except FileExistsError:
                if _digest(target.read_bytes()) != content_hash:
                    raise WarehouseError("existing data object is corrupted") from None
            marker = stage / "manifest.json"
            marker.write_text(json.dumps(manifest, sort_keys=True, allow_nan=False))
            locks = self.root / "_locks"
            locks.mkdir(exist_ok=True)
            with (locks / snapshot_id).open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if list((self.root / "manifests").glob(f"*/*/{snapshot_id}.json")):
                    raise WarehouseError(f"snapshot {snapshot_id!r} already published")
                (manifests / f"{snapshot_id}.json").hardlink_to(marker)
            return manifest
        finally:
            shutil.rmtree(stage)

    def load(self, snapshot_id: str) -> tuple[dict[str, Any], pa.Table]:
        _token(snapshot_id)
        try:
            matches = list((self.root / "manifests").glob(f"*/*/{snapshot_id}.json"))
            if len(matches) != 1:
                raise WarehouseError("snapshot id missing or ambiguous")
            manifest = json.loads(matches[0].read_text())
            digest = manifest["sha256"]
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise WarehouseError("invalid content hash")
            namespace = manifest["namespace"]
            provider = _token(manifest["provider"])
            dataset = _token(manifest["dataset"])
            schema = _token(str(manifest["schema_version"]))
            date = datetime.fromtimestamp(manifest["event_start"], UTC).date().isoformat()
            if namespace == "ledger":
                expected = f"ledger/{provider}/v{schema}/date={date}/part-{digest}.parquet"
            elif namespace == "external":
                expected = (
                    f"external/{provider}/{dataset}/v{schema}/"
                    f"snapshot={snapshot_id}/part-{digest}.parquet"
                )
            else:
                raise WarehouseError("unknown warehouse namespace")
            if manifest["snapshot_id"] != snapshot_id or manifest["path"] != expected:
                raise WarehouseError("manifest identity/path mismatch")
            body = (self.root / expected).read_bytes()
            if _digest(body) != digest:
                raise WarehouseError("snapshot content hash mismatch")
            table = pq.read_table(pa.BufferReader(body))
            if table.num_rows != manifest["row_count"]:
                raise WarehouseError("snapshot row count mismatch")
            return manifest, table
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise WarehouseError(f"cannot load snapshot {snapshot_id!r}") from exc

    def list_snapshots(self, instrument_id: str) -> list[dict[str, Any]]:
        """List validated published snapshots for one exact instrument identity."""
        result = []
        for path in sorted((self.root / "manifests").glob("*/*/*.json")):
            manifest, _ = self.load(path.stem)
            if manifest["instrument_id"] == instrument_id:
                result.append(manifest)
        return result
