"""/instruments and /market-data/status routes (A05 output contracts).

Mounted into the control plane in ``api/main.py`` as an A03/A04-precedent
proposal through the api owner (see the A05 scope guard). The routes are
read-only over the bundled registry and recordings — no external feeds, no
secrets, no DB — so they stay deterministic and CI-checkable.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from algobots.instruments.registry import UnknownInstrumentError, default_registry
from algobots.marketdata.recorded import load_recording
from algobots.marketdata.replay import ReplayFeed
from algobots.marketdata.status import watchlist_status

__all__ = ["instruments_router", "marketdata_router"]

instruments_router = APIRouter(prefix="/instruments", tags=["instruments"])
marketdata_router = APIRouter(prefix="/market-data", tags=["market-data"])


@instruments_router.get("")
def list_instruments() -> dict:
    """The canonical registry: every executable identity with its precision metadata."""
    registry = default_registry()
    return {
        "count": len(registry),
        "instruments": [i.model_dump(mode="json") for i in registry.list()],
    }


@instruments_router.get("/{instrument_id}")
def get_instrument(instrument_id: str) -> dict:
    registry = default_registry()
    try:
        instrument = registry.get(instrument_id)
    except UnknownInstrumentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return instrument.model_dump(mode="json")


@marketdata_router.get("/status")
def market_data_status(
    ids: str | None = Query(default=None, description="comma-separated executable IDs"),
    as_of: datetime | None = Query(default=None, description="as-of time (offset-aware)"),
) -> dict:
    """Watchlist status: market state, data timestamps, freshness, precision."""
    requested = tuple(i.strip() for i in ids.split(",")) if ids else None
    if requested:
        registry = default_registry()
        unknown = [i for i in requested if i not in registry]
        if unknown:
            raise HTTPException(status_code=404, detail=f"unknown instrument IDs: {unknown}")
    rows = watchlist_status(
        instrument_ids=requested, feed=ReplayFeed(load_recording()), as_of=as_of
    )
    return {"count": len(rows), "statuses": rows}
