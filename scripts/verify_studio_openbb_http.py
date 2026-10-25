"""Operator acceptance: provision one invite, then use only invited-session HTTP.

Run in the API container. Credentials remain in memory and never enter evidence.
The invited tenant and its immutable result remain available for inspection.
"""

import json
import secrets
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from algobots.api.database import get_session_factory
from algobots.api.models import InviteCode, User, UserRole

BASE = "http://100.82.57.72:8201"
headers = {}


def http(path, payload=None, expected=200):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        ("http://127.0.0.1:8000" if path.startswith("/api/auth/") else BASE) + path,
        data=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=100) as response:
            assert response.status == expected, response.status
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"HTTP {exc.code} {path}: {exc.read().decode()}") from None


with get_session_factory()() as db:
    owner = db.scalar(select(User).where(User.role == UserRole.OWNER, User.is_active.is_(True)))
    assert owner is not None
    code = secrets.token_urlsafe(24)
    db.add(
        InviteCode(
            code=code,
            created_by_user_id=owner.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()

email, password = f"alg3421-{secrets.token_hex(6)}@example.com", secrets.token_urlsafe(32)
user = http(
    "/api/auth/register",
    dict(email=email, password=password, display_name="OpenBB Studio acceptance", invite_code=code),
    expected=201,
)
token = http("/api/auth/login", dict(email=email, password=password))["access_token"]
headers["Authorization"] = "Bearer " + token
snapshots = http("/api/studio/snapshots?instrument_id=SPY.NYSE")["snapshots"]
snapshot = next(s for s in snapshots if s["snapshot_id"] == "openbb-spy-60430be3251945a6")
draft = json.loads(Path("/tmp/alg3421-draft.json").read_text())
created = http("/api/studio/strategies", draft, expected=201)
url = f"/api/studio/strategies/{created['id']}"
artifact = http(url + "/compile", {}, expected=201)
result = http(url + "/backtest", {"snapshot_id": snapshot["snapshot_id"]}, expected=201)
repeat = http(url + "/backtest", {"snapshot_id": snapshot["snapshot_id"]})
assert repeat["id"] == result["id"]
assert result["dataset"]["sha256"] == snapshot["sha256"]
assert result["engine"]["iterations"] == snapshot["row_count"]
assert result["executor"] == "NautilusTrader BacktestEngine 2.0.0rc6"
assert result["trades"]
assert all(float(t["event"]) / 1e9 > t["signal_ts"] for t in result["trades"])
assert len(http(url + "/backtests")["backtests"]) == 1
assert result["evidence"]["dataset_sha256"] == snapshot["sha256"]
print(
    json.dumps(
        dict(
            before="422 signals.entry (CEO walkthrough)",
            after="201 created; 200 repeat",
            invited_user_id=user["id"],
            draft_id=created["id"],
            snapshot_id=snapshot["snapshot_id"],
            idempotent=True,
            result=result,
        ),
        sort_keys=True,
    )
)
