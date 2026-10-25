"""ALG-3414: the NoFX Studio funder surface rides the real invite gate.

Login/register/logout in NoFX's dialect, owner-minted invites (single use,
expiring, revocable), funder revocation that kills live sessions, tenant-scoped
Studio configs, and the live evidence feed correlating decisions with actual
Nautilus fill receipts — all behind a live session, never a synthetic principal.
"""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from algobots.api.config import get_settings
from algobots.api.database import get_session_factory
from algobots.api.models import InviteCode
from algobots.demo import router as demo_router
from tests.conftest import TEST_PASSWORD


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _nofx_login(client: TestClient, email: str, password: str = TEST_PASSWORD):
    return client.post("/api/nofx/login", json={"email": email, "password": password})


def _mint(client: TestClient, owner_token: str) -> dict:
    r = client.post("/api/nofx/studio/invites", headers=_h(owner_token))
    assert r.status_code == 201, r.text
    return r.json()


def _register(client: TestClient, code: str | None, email: str | None = None):
    email = email or f"funder-{uuid.uuid4().hex[:10]}@example.com"
    body = {"email": email, "password": TEST_PASSWORD, "lang": "en"}
    if code is not None:
        body["beta_code"] = code
    return email, client.post("/api/nofx/register", json=body)


@pytest.fixture()
def owner_token(client: TestClient, founder: dict) -> str:
    r = _nofx_login(client, founder["email"])
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def funder(client: TestClient, owner_token: str) -> dict:
    inv = _mint(client, owner_token)
    email, r = _register(client, inv["code"])
    assert r.status_code == 200, r.text
    return {**r.json(), "invite_id": inv["id"]}


def test_config_is_public_and_invite_only(client):
    body = client.get("/api/nofx/config").json()
    assert body == {"initialized": True, "beta_mode": True, "registration_enabled": True}


def test_login_returns_nofx_shape_and_denies_bad_password(client, founder):
    r = _nofx_login(client, founder["email"])
    assert r.status_code == 200
    body = r.json()
    assert {"token", "user_id", "email", "tenant_id"} <= body.keys()
    assert body["email"] == founder["email"] and body["role"] == "owner"
    bad = _nofx_login(client, founder["email"], "wrong-password-123")
    assert bad.status_code == 401 and bad.json() == {"error": "Invalid email or password"}


def test_owner_mints_and_funder_signs_in_once(client, owner_token, funder):
    me = client.get("/api/nofx/studio/me", headers=_h(funder["token"])).json()
    assert me["role"] == "member" and me["can_mint_invites"] is False
    # the registration token is the session: no second login needed
    assert client.get("/api/nofx/strategies", headers=_h(funder["token"])).status_code == 200
    listed = client.get("/api/nofx/studio/invites", headers=_h(owner_token)).json()["invites"]
    row = next(i for i in listed if i["id"] == funder["invite_id"])
    assert row["state"] == "active" and row["code"] is None  # code shown once, at mint


def test_members_cannot_mint(client, funder):
    r = client.post("/api/nofx/studio/invites", headers=_h(funder["token"]))
    assert r.status_code == 403


def test_register_denials(client, owner_token):
    _, r = _register(client, None)
    assert r.status_code == 400 and "invite code" in r.json()["error"]
    _, r = _register(client, "ALG-not-a-real-code")
    assert r.status_code == 409 and r.json()["error"] == "Invalid invite code"
    inv = _mint(client, owner_token)
    _, ok = _register(client, inv["code"])
    assert ok.status_code == 200
    _, reused = _register(client, inv["code"])
    assert reused.status_code == 409 and reused.json()["error"] == "Invite code already used"


def test_expired_invite_is_refused(client, owner_token):
    inv = _mint(client, owner_token)
    db = get_session_factory()()
    try:
        row = db.get(InviteCode, uuid.UUID(inv["id"]))
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    _, r = _register(client, inv["code"])
    assert r.status_code == 409 and r.json()["error"] == "Invite code expired"


def test_revoking_unclaimed_invite_expires_it(client, owner_token):
    inv = _mint(client, owner_token)
    r = client.post(f"/api/nofx/studio/invites/{inv['id']}/revoke", headers=_h(owner_token))
    assert r.status_code == 200 and r.json()["state"] == "expired"
    _, reg = _register(client, inv["code"])
    assert reg.status_code == 409 and reg.json()["error"] == "Invite code expired"


def test_revoking_funder_kills_sessions_and_login(client, owner_token, funder):
    assert client.get("/api/nofx/studio/live", headers=_h(funder["token"])).status_code == 200
    r = client.post(
        f"/api/nofx/studio/invites/{funder['invite_id']}/revoke", headers=_h(owner_token)
    )
    assert r.status_code == 200 and r.json()["state"] == "revoked"
    assert client.get("/api/nofx/studio/live", headers=_h(funder["token"])).status_code == 401
    again = _nofx_login(client, funder["email"])
    assert again.status_code == 401 and again.json()["error"] == "Access revoked"


def test_logout_revokes_the_token(client, funder):
    assert client.post("/api/nofx/logout", headers=_h(funder["token"])).status_code == 200
    assert client.get("/api/nofx/studio/me", headers=_h(funder["token"])).status_code == 401


def test_live_requires_a_session(client):
    assert client.get("/api/nofx/studio/live").status_code == 401
    assert client.get("/api/nofx/studio/live", headers=_h("not-a-jwt")).status_code == 401


def test_studio_configs_are_tenant_scoped(client, owner_token, funder):
    h = _h(funder["token"])
    created = client.post(
        "/api/nofx/strategies",
        headers=h,
        json={"name": "Kalshi momentum", "description": "d", "config": {"a": 1}},
    ).json()
    sid = created["id"]
    upd = client.put(
        f"/api/nofx/strategies/{sid}",
        headers=h,
        json={"name": "Kalshi momentum", "description": "d2", "config": {"a": 2}},
    ).json()
    assert upd["config"] == {"a": 2} and upd["execution"] == "config-only"
    assert client.post(f"/api/nofx/strategies/{sid}/activate", headers=h).json()["is_active"]
    assert client.get("/api/nofx/strategies/active", headers=h).json()["id"] == sid
    dup = client.post(f"/api/nofx/strategies/{sid}/duplicate", headers=h).json()
    assert dup["is_active"] is False and dup["config"] == {"a": 2}
    # another tenant (the owner's personal tenant) can neither list nor read it
    oh = _h(owner_token)
    assert sid not in {
        s["id"] for s in client.get("/api/nofx/strategies", headers=oh).json()["strategies"]
    }
    assert client.get(f"/api/nofx/strategies/{sid}", headers=oh).status_code == 404
    assert client.delete(f"/api/nofx/strategies/{sid}", headers=oh).status_code == 404
    assert client.delete(f"/api/nofx/strategies/{sid}", headers=h).status_code == 200


@pytest.fixture()
def demo_state(tmp_path, monkeypatch):
    now = time.time()
    feed = tmp_path / "observations.jsonl"
    feed.write_text(
        json.dumps(
            {
                "event": "KXBTC15M-26OCT230545",
                "market": "KXBTC15M-26OCT230545-45",
                "strike": 81531.57,
                "ts": now - 60,
                "mkt_yes_bid": 0.6,
                "mkt_yes_ask": 0.61,
                "outcome": None,
            }
        )
        + "\n"
    )
    log = [
        {
            "decision_id": "coin:KXBTC15M-26OCT230530",
            "strategy": "coin",
            "instrument_id": "KXBTC15M-26OCT230530",
            "side": "NO",
            "status": "VALID",
            "decided_at": "2026-10-23T09:15:16+00:00",
            "reason": "coin -> tails -> NO",
            "execution": {"status": "FILLED", "qty": 19, "fill_px": "0.52", "stake": "9.88"},
        },
        {
            "decision_id": "laya:KXBTC15M-26OCT230530",
            "strategy": "laya",
            "instrument_id": "KXBTC15M-26OCT230530",
            "side": "YES",
            "status": "VALID",
            "decided_at": "2026-10-23T09:15:16+00:00",
            "reason": "edge +3.7pp -> YES; daily-loss envelope (-40 USD) exhausted",
            "execution": {"status": "BLOCKED", "qty": 0, "fill_px": "0", "stake": "0"},
        },
    ]
    (tmp_path / "decision_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log))
    workers = tmp_path / "workers"
    workers.mkdir()
    fill = {
        "client_order_id": "O-20261023-091516-COIN-COIN-48",
        "trade_id": "T-abc-001",
        "instrument": "KXBTC15M-26OCT230530-NO.PAPER_COIN",
        "event": "KXBTC15M-26OCT230530",
        "qty": "19",
        "px": "0.52",
    }
    (workers / "coin.json").write_text(
        json.dumps(
            {
                "account": "coin",
                "phase": "ready",
                "last_heartbeat": now,
                "mode": "paper",
                "execution": "sandbox",
                "fills": [fill],
                "report": {"positions": []},
            }
        )
    )
    (workers / "laya.json").write_text(
        json.dumps({"account": "laya", "phase": "ready", "last_heartbeat": now - 3600, "fills": []})
    )
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(feed))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    get_settings.cache_clear()

    def _no_ledger(scope):
        raise RuntimeError("no feed history in this test")

    monkeypatch.setattr(demo_router, "_quality", _no_ledger)
    yield tmp_path
    get_settings.cache_clear()


def test_live_correlates_decisions_with_nautilus_receipts(client, funder, demo_state):
    body = client.get("/api/nofx/studio/live", headers=_h(funder["token"])).json()
    assert body["environment"]["mode"] == "paper"
    assert body["feed"]["state"] == "live" and body["feed"]["event"] == "KXBTC15M-26OCT230545"
    by_id = {d["decision_id"]: d for d in body["decisions"]}
    coin = by_id["coin:KXBTC15M-26OCT230530"]
    assert coin["receipt"]["client_order_id"] == "O-20261023-091516-COIN-COIN-48"
    assert coin["receipt"]["trade_id"] == "T-abc-001"
    laya = by_id["laya:KXBTC15M-26OCT230530"]
    assert laya["risk_blocked"] and laya["receipt"] is None
    assert "daily-loss" in laya["reason"]
    states = {w["account"]: w["state"] for w in body["workers"]}
    assert states["coin"] == "ready" and states["laya"] == "stale"
    assert states["jev"] == "unavailable"  # no heartbeat file: said so, not invented
    assert body["decisions_error"].startswith("ledger sync unavailable")


def test_live_reports_stale_and_missing_feed(client, funder, demo_state, monkeypatch):
    feed = demo_state / "observations.jsonl"
    feed.write_text(json.dumps({"event": "E", "ts": time.time() - 3600}) + "\n")
    assert (
        client.get("/api/nofx/studio/live", headers=_h(funder["token"])).json()["feed"]["state"]
        == "stale"
    )
    feed.unlink()
    f = client.get("/api/nofx/studio/live", headers=_h(funder["token"])).json()["feed"]
    assert f["state"] == "unavailable"


def test_walkthrough_endpoints_require_session(client):
    for path in ("/api/data", "/api/leaderboard", "/api/nofx/data", "/api/nofx/leaderboard"):
        assert client.get(path).status_code == 401


def test_default_strategy_seed_edit_activate(client, funder):
    h = _h(funder["token"])
    rows = client.get("/api/nofx/strategies", headers=h).json()["strategies"]
    assert len(rows) == 1
    seed = rows[0]
    assert seed["config"]["demo_worker"]["p_source"] == "mom3x15m/vol20"
    assert seed["config"]["demo_worker"]["max_daily_loss"] == "40"
    again = client.get("/api/nofx/strategies", headers=h).json()["strategies"]
    assert [r["id"] for r in again] == [seed["id"]]
    cfg = seed["config"]
    cfg["ai_config"]["custom_prompt"] = "edited draft"
    edited = client.put(
        f"/api/nofx/strategies/{seed['id']}", headers=h, json={"name": seed["name"], "config": cfg}
    )
    assert edited.status_code == 200 and edited.json()["config"] == cfg
    active = client.post(f"/api/nofx/strategies/{seed['id']}/activate", headers=h)
    assert active.status_code == 200 and active.json()["is_active"] is True
    assert active.json()["execution"] == "config-only"


def test_data_preserves_live_probabilities_and_counts(client, funder, demo_state):
    path = demo_state / "observations.jsonl"
    row = json.loads(path.read_text())
    row.update(p=0.63, p_source="mom3x15m/vol20")
    path.write_text(json.dumps(row) + "\ninvalid json\n")
    response = client.get("/api/data", headers=_h(funder["token"]))
    assert response.status_code == 200
    data = response.json()
    assert data["feed"]["state"] == "live" and data["row_count"] == 1
    assert data["observations"][0]["p"] == 0.63
    assert data["counts"]["logged_total"] == 2
    path.unlink()
    missing = client.get("/api/nofx/data", headers=_h(funder["token"])).json()
    assert missing["feed"]["state"] == "unavailable" and missing["observations"] == []


def test_leaderboard_uses_scoped_decision_scores(client, funder, monkeypatch):
    from types import SimpleNamespace

    from algobots.demo.decisions import Score

    def quality(scope):
        assert "laya" in scope.accounts
        return SimpleNamespace(
            scores={"laya": Score("laya", 40, 24, 0.6, 0.23, 0.1, 0.05, "no edge proven", False)},
            logged=45,
            settled=[None] * 40,
        )

    monkeypatch.setattr(demo_router, "_quality", quality)
    from decimal import Decimal

    monkeypatch.setattr(
        demo_router,
        "_ledger",
        lambda: (
            SimpleNamespace(
                books={
                    "laya": SimpleNamespace(
                        curve=[(123.0, Decimal("240.13")), (124.0, Decimal("245.09"))]
                    ),
                    "not-granted": SimpleNamespace(curve=[(123.0, Decimal("99999"))]),
                }
            ),
            "2026-10-23",
        ),
    )
    result = client.get("/api/leaderboard", headers=_h(funder["token"])).json()
    assert result["accounts"][0]["hit_rate"] == 0.6
    assert result["accounts"][0]["brier"] == 0.23
    assert result["settled"] == 40
    assert result["equity_curves"] == {
        "laya": [
            {"ts": 123.0, "equity": "240.13"},
            {"ts": 124.0, "equity": "245.09"},
        ]
    }
    assert "replay" in result["equity_source"]


def test_empty_tenant_seed_happens_once(client, funder):
    """ALG-3352: repeat GETs on an empty tenant keep exactly one default row."""
    first = client.get("/api/nofx/strategies", headers=_h(funder["token"])).json()
    assert len(first["strategies"]) == 1
    for _ in range(3):
        again = client.get("/api/nofx/strategies", headers=_h(funder["token"])).json()
        assert len(again["strategies"]) == 1
        assert again["strategies"][0]["id"] == first["strategies"][0]["id"]


def test_seed_lock_is_pg_only_and_rechecks():
    """The advisory lock guards the live Postgres race; sqlite tests skip it."""
    from unittest.mock import MagicMock

    from algobots.api.routers import nofx

    nofx._seed_lock(MagicMock(), MagicMock())  # sqlite bind: no execute expected

    pg_session = MagicMock()
    pg_bind = MagicMock()
    pg_bind.dialect.name = "postgresql"
    pg_session.get_bind.return_value = pg_bind
    nofx._seed_lock(pg_session, MagicMock())
    assert "pg_advisory_xact_lock" in str(pg_session.execute.call_args[0][0])
