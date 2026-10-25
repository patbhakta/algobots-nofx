"""Publish real Nautilus objects through its catalog API, with read-back proof.

Each snapshot owns a separate catalog directory. Existing catalogs are never
opened for writing: Nautilus write_data may otherwise overwrite matching files.
The default seam is the FunnyTree ntl_catalog mount used by quantlab.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from nautilus_trader.model.data import Bar
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from algobots.warehouse import WarehouseError, _token

DEFAULT_CATALOG_ROOT = Path("/mnt/funnytree/algobots/ntl_catalog")


def publish_bars(
    snapshot_id: str,
    instrument: Instrument,
    bars: list[Bar],
    root: Path = DEFAULT_CATALOG_ROOT,
) -> Path:
    """Store instrument and external BarType bars; require lossless Nautilus query.

    Event/init timestamps are already integer nanoseconds in Nautilus objects.
    The caller must construct bars from recorded OHLC, never settlement outcomes.
    """
    _token(snapshot_id)
    if not bars:
        raise WarehouseError("catalog bars required")
    bar_type = bars[0].bar_type
    if bar_type.instrument_id != instrument.id or any(b.bar_type != bar_type for b in bars):
        raise WarehouseError("catalog instrument/bar type mismatch")
    if any(b.ts_init < b.ts_event for b in bars):
        raise WarehouseError("bar initialization predates event")
    if any(a.ts_event >= b.ts_event for a, b in zip(bars, bars[1:], strict=False)):
        raise WarehouseError("catalog bars must be strictly ordered")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / snapshot_id
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    lock = root / f".{snapshot_id}.lock"
    locked = False
    try:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise WarehouseError("catalog publication already in progress") from None
        os.close(fd)
        locked = True
        if target.exists():
            raise WarehouseError("catalog snapshot already published")
        catalog = ParquetDataCatalog(str(stage))
        catalog.write_data([instrument])
        catalog.write_data(bars)
        replay = catalog.query(Bar)
        if replay != bars or not catalog.instruments():
            raise WarehouseError("Nautilus catalog read-back mismatch")
        stage.rename(target)
        return target
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if locked:
            lock.unlink()
