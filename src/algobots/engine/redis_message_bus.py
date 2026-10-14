"""Canonical Nautilus Redis event-egress configuration.

Targets the `nautilus-trader>=1.231` pin in the `workers` extra. Published
stream keys are `trader-{trader_id}:{streams_prefix}:{topic}`, so the trader
prefix precedes `streams_prefix` (an `algobots*` glob will not match them).
See `scripts/phase0_redis_egress.py` for the sandbox node that exercises this.
"""

from __future__ import annotations

import os

from nautilus_trader.common.config import DatabaseConfig
from nautilus_trader.config import MessageBusConfig
from nautilus_trader.model.data import QuoteTick


def redis_message_bus_config() -> MessageBusConfig:
    """JSON streams for durable events, excluding high-volume quote ticks."""
    return MessageBusConfig(
        database=DatabaseConfig(
            type="redis",
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        ),
        encoding="json",
        timestamps_as_iso8601=True,
        stream_per_topic=True,
        streams_prefix="algobots",
        types_filter=[QuoteTick],
    )
