"""ALG-3266: registry-backed Accounts pane, LIVE gate, Semi-auto broadcast + Action Center."""

import json
from uuid import UUID

import pytest
from sqlalchemy import select

from algobots.api.approvals.models import ActionLedger, ApprovalRequest
from algobots.api.config import get_settings
from algobots.api.database import get_session_factory
from algobots.api.models import DEMO_OWNER_EMAIL, Account, Order, User
from algobots.demo import accounts as A
from algobots.demo import killswitch
from algobots.demo import ledger as L
from algobots.demo.page import Registry, render


@pytest.fixture()
def db(migrated_db):
    session = get_session_factory()()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def quiet_feed(tmp_path, monkeypatch):
    """No feed rows and a private kill switch: no strategy halts unless a test adds one."""
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_feed_path", str(tmp_path / "none.jsonl"))
    monkeypatch.setattr(settings, "demo_state_dir", str(tmp_path / "state"))
    return settings


@pytest.fixture()
def owner(db):
    return A.ensure_seeded(db)


def _by_label(db, owner) -> dict[str, Account]:
    return {a.label: a for a in A.accounts(db, owner)}


def test_seed_is_idempotent_paper_by_default_and_never_bootstraps(db, owner):
    again = A.ensure_seeded(db)
    assert again.id == owner.id and not owner.is_active
    accts = A.accounts(db, owner)
    assert [a.label for a in accts] == list(A.SEED)
    assert {a.mode for a in accts if a.label != "Pat · Kalshi live"} == {"paper"}
    assert db.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL)).password_hash == "!"


def test_accounts_pane_reads_registry_rows(client, db, owner):
    html = client.get("/demo").text
    for label in A.SEED:
        assert label in html
    assert "Semi-auto" in html and "Auto" in html
    assert 'data-environment="LIVE"' in html and "paper adapter" in html
    # a row added to the registry shows up without code changes
    db.add(Account(user_id=owner.id, label="Registry-only probe", broker="alpaca"))
    db.commit()
    rows = client.get("/demo/api/accounts").json()["accounts"]
    probe = next(r for r in rows if r["label"] == "Registry-only probe")
    assert probe["environment"] == "PAPER" and probe["approval_mode"] == "auto"
    assert "Registry-only probe" in client.get("/demo").text


def test_live_account_actions_disabled_with_reason_and_never_fill(client, db, owner):
    live = _by_label(db, owner)["Pat · Kalshi live"]
    row = next(
        r for r in client.get("/demo/api/accounts").json()["accounts"] if r["id"] == str(live.id)
    )
    assert row["environment"] == "LIVE"
    assert row["order_actions_disabled"] == "live gated: G-live not passed"
    html = client.get("/demo").text
    assert f'data-account="{live.id}" data-environment="LIVE" aria-disabled="true"' in html
    assert f'data-leg-blocked="{live.id}"' in html  # ticket: no input for the LIVE leg
    assert f'value="{live.id}"' not in html
    # even if posted directly, the LIVE leg is refused before an order row exists
    ticket = A.broadcast(db, owner, [live.id], side="YES", qty=5, actor="test")
    assert [(leg.status, leg.reason) for leg in ticket.legs] == [
        ("blocked", "live gated: G-live not passed")
    ]
    assert ticket.state == "blocked"
    assert db.scalars(select(Order).where(Order.account_id == live.id)).all() == []
    with pytest.raises(A.LiveGated):
        A.adapter_for(live)
    # an active LIVE account is gated too, not just a paused one
    live.status = "active"
    assert A.order_block_reason(live) == "live gated: G-live not passed"
    db.rollback()


def test_semi_auto_broadcast_part_queued_then_approve_fills_with_audit(client, db, owner):
    by = _by_label(db, owner)
    laya, semi, live = (
        by[L.STRATEGIES["laya"]],
        by["Pat · Kalshi semi-auto"],
        by["Pat · Kalshi live"],
    )
    r = client.post(
        "/demo/ticket",
        data={"account": [str(laya.id), str(semi.id), str(live.id)], "side": "YES", "qty": "10"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    ticket = A.last_ticket(db, owner)
    assert ticket["state"] == "part_queued"
    assert [leg["status"] for leg in ticket["legs"]] == ["filled", "parked", "blocked"]
    filled = db.get(Order, UUID(ticket["legs"][0]["order_id"]))
    assert filled.status == "filled"

    req_id = ticket["legs"][1]["request_id"]
    html = client.get("/demo").text
    assert f'action="/demo/approvals/{req_id}"' in html and "part_queued" in html

    r = client.post(
        f"/demo/approvals/{req_id}",
        data={"verdict": "approved", "actor": "Pat"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.expire_all()
    req = db.get(ApprovalRequest, UUID(req_id))
    assert req.status == "approved"
    assert db.get(Order, req.order_id).status == "filled"
    audit = db.scalars(
        select(ActionLedger)
        .where(ActionLedger.subject_id == req.id)
        .order_by(ActionLedger.created_at)
    ).all()
    assert [a.action for a in audit] == ["order_parked", "approval_approved", "broadcast_reported"]
    assert "Pat via dashboard" in audit[1].reason
    assert json.loads(audit[2].detail_json)["state"] == "sent"
    assert req_id not in client.get("/demo/api/accounts").text


def test_reject_writes_audit_and_cancels(db, owner):
    semi = _by_label(db, owner)["Pat · Kalshi semi-auto"]
    ticket = A.broadcast(db, owner, [semi.id], side="NO", qty=3, actor="test")
    assert ticket.state == "queued"
    req, out = A.decide(db, owner, ticket.legs[0].request_id, "rejected", actor="Pat")
    assert out is None and req.status == "rejected"
    assert db.get(Order, req.order_id).status == "cancelled"
    actions = db.scalars(select(ActionLedger.action).where(ActionLedger.subject_id == req.id))
    assert "approval_rejected" in list(actions)


def test_kill_switch_halts_every_leg(db, owner):
    laya = _by_label(db, owner)[L.STRATEGIES["laya"]]
    ticket = A.broadcast(
        db, owner, [laya.id], side="YES", qty=1, actor="t", halts={laya.id: "halted — kill switch"}
    )
    assert ticket.legs[0].status == "blocked" and ticket.state == "blocked"


def test_page_renders_without_registry():
    html = render(L.build([]), start="2026-10-03")
    assert "Account registry unavailable" in html


def test_registry_render_marks_live_badge(db, owner):
    reg = Registry(
        accounts=[(a, A.session_health(db, a)) for a in A.accounts(db, owner)], can_trade=True
    )
    html = render(L.build([]), start="2026-10-03", registry=reg)
    assert html.count('class="badge env-live"') >= 2  # Accounts row + ticket leg


def test_ticket_route_applies_kill_switch_to_every_leg(client, db, owner, quiet_feed):
    killswitch.set_engaged(quiet_feed.demo_state_dir, True, actor="test")
    semi = _by_label(db, owner)["Pat · Kalshi semi-auto"]
    client.post("/demo/ticket", data={"account": [str(semi.id)], "side": "NO", "qty": "2"})
    ticket = A.last_ticket(db, owner)
    assert ticket["state"] == "blocked"
    assert ticket["legs"][0]["reason"] == "halted — kill switch"


def test_partial_grant_hides_ticket_only_accounts_and_refuses_trading(client, db, owner):
    from algobots.api.main import app
    from algobots.contracts.identity import Grant, IdentityKind, Principal
    from algobots.demo.scope import Scope, current_scope

    who = Principal(
        schema_version=Principal.contract_version,
        principal_id="laya-only",
        kind=IdentityKind.USER,
        tenant_id="demo",
        grants=(Grant.ACCOUNT_READ,),
    )
    app.dependency_overrides[current_scope] = lambda: Scope.of(who, {"laya"})
    try:
        labels = [a["label"] for a in client.get("/demo/api/accounts").json()["accounts"]]
        assert labels == [L.STRATEGIES["laya"]]
        html = client.get("/demo").text
        assert "Pat · Kalshi live" not in html and "needs a grant on every account" in html
        semi = _by_label(db, owner)["Pat · Kalshi semi-auto"]
        r = client.post("/demo/ticket", data={"account": [str(semi.id)], "side": "YES"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(current_scope, None)
