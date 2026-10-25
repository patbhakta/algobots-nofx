"""Stable gateway admission identity for one deployment's market decision.

One frozen deployment may enter each Kalshi market once. Retries and process
restarts must reuse this key through the gateway's persistent idempotency path.
Direction, quantity, current time and process identity deliberately do not enter
the key: a changed decision for the same market must conflict at admission,
rather than create another trade. This helper alone does not provide dedupe;
callers must admit through the gateway, never publish directly to Redis.
"""

from __future__ import annotations

import hashlib
import json
import re
from uuid import UUID


def deployment_order_id(deployment_id: UUID | str, artifact_hash: str, market: str) -> str:
    """Return a versioned, contract-safe client order ID, independent of restart."""
    deployment = str(UUID(str(deployment_id)))
    if not isinstance(artifact_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact_hash):
        raise ValueError("artifact_hash must be a canonical SHA-256 digest")
    if (
        not isinstance(market, str)
        or not market
        or market != market.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in market)
    ):
        raise ValueError("market must be a nonempty canonical market identifier")
    payload = json.dumps([deployment, artifact_hash, market], separators=(",", ":"))
    # 240 digest bits fit with a version prefix in the command's 64-char limit.
    return "dp1-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:60]
