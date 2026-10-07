"""ALG-3260 /demo server-side account scope: grants, 403/404, no cross-account leak, states."""

import json
import re

import pytest

from algobots.contracts.identity import Grant, IdentityKind, Principal
from algobots.demo import ledger as L
from algobots.demo.page import render
from algobots.demo.scope import Scope, current_scope, narrow

ENDPOINTS = (
    "/demo/api/positions",
    "/demo/api/orders",
    "/demo/api/workers",
    "/demo/api/decisions",
    "/demo/api/quality",
)


def _scope(*accounts: str) -> Scope:
    who = Principal(
        schema_version="1.0",
        principal_id="p-test",
        kind=IdentityKind.USER,
        tenant_id="t-test",
        grants=(Grant.ACCOUNT_READ,),
    )
    return Scope.of(who, set(accounts))


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from algobots.api.config import get_settings
    from algobots.api.main import app

    feed = tmp_path / "observations.jsonl"
    rows = [
        {
            "event": f"E{i}",
            "strike": 1,
            "outcome": i % 2,
            "ts": 1791244800 + i * 900,
            "p": 0.6,
            "conf": 0.1,
            "jev_choice": "up",
            "jev_conf": 0.5,
            "jev_p": 0.6,
        }
        for i in range(5)
    ]
    feed.write_text("\n".join(json.dumps(r) for r in rows))
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(feed))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ALGOBOTS_DEMO_START", "2026-10-06")
    get_settings.cache_clear()

    def grant(*accounts: str) -> TestClient:
        app.dependency_overrides[current_scope] = lambda: _scope(*accounts)
        return TestClient(app)

    try:
        yield grant
    finally:
        app.dependency_overrides.pop(current_scope, None)
        get_settings.cache_clear()


def test_default_demo_identity_still_runs_the_grant_check(client, monkeypatch):
    from algobots.api.config import get_settings

    monkeypatch.setenv("ALGOBOTS_DEMO_ACCOUNT_GRANTS", "laya,jev")
    get_settings.cache_clear()
    s = current_scope()
    assert s.principal.principal_id == "demo-viewer" and s.accounts == ("laya", "jev")


def test_granted_account_renders(client):
    r = client("laya", "jev", "coin").get("/demo?account=jev")
    assert r.status_code == 200 and 'class="acct sel" data-account="jev"' in r.text
    assert r.headers["cache-control"] == "no-store"


def test_ungranted_deep_link_is_403_on_page_and_every_json_endpoint(client):
    c = client("laya")
    page = c.get("/demo?account=jev")
    assert page.status_code == 403 and 'data-state="denied"' in page.text
    assert "Jev zero-shot" not in page.text and "E0" not in page.text  # no fallback to All
    for path in ENDPOINTS:
        r = c.get(f"{path}?account=jev")
        assert r.status_code == 403, path
        assert r.json()["detail"]["state"] == "denied"
    assert c.get("/demo/api/orders?account=nope").status_code == 404
    assert c.get("/demo?account=nope").status_code == 404


def test_aggregate_denied_without_any_grant(client):
    c = client()
    assert c.get("/demo").status_code == 403
    for path in (*ENDPOINTS, "/demo/api/state"):
        assert c.get(path).status_code == 403, path


def test_partial_grant_aggregate_shows_only_granted_accounts(client):
    c = client("laya", "coin")
    page = c.get("/demo").text
    assert set(re.findall(r'class="acct(?: sel)?" data-account="(\w+)"', page)) == {
        "all",
        "laya",
        "coin",
    }
    assert "Jev zero-shot" not in page
    orders = c.get("/demo/api/orders?limit=5000").json()["orders"]
    assert orders and {o["account"] for o in orders} == {"laya", "coin"}
    assert {w["account"] for w in c.get("/demo/api/workers").json()["workers"]} <= {"laya", "coin"}
    dq = c.get("/demo/api/decisions").json()
    assert set(dq["scores"]) == {"laya", "coin"} and dq["logged"] == 10
    assert dq["losses"] and {x["strategy"] for x in dq["losses"]} <= {"laya", "coin"}
    # the kill switch halts every account, so a partial grant cannot flip it
    assert c.post("/demo/kill-switch", data={"engaged": "on"}).status_code == 403


def test_context_switch_response_has_no_other_account_ids(client):
    c = client("laya", "jev", "coin")
    every = {o["id"] for o in c.get("/demo/api/orders?limit=5000").json()["orders"]}
    jev = c.get("/demo/api/orders?account=jev&limit=5000").json()["orders"]
    mine = {o["id"] for o in jev}
    assert mine and all(i.startswith("jev:") for i in mine)
    page = c.get("/demo?account=jev").text
    others = every - mine
    assert others and not any(f'data-order="{i}"' in page for i in others)
    assert {p["account"] for p in c.get("/demo/api/positions?account=jev").json()["positions"]} <= {
        "jev"
    }


def test_narrow_drops_ungranted_books():
    lg = L.build([])
    assert set(narrow(lg, _scope("coin")).books) == {"coin"}


def test_one_line_states_disconnected_empty_connected():
    lg = L.build([])
    html = render(narrow(lg, _scope("laya")), start="x", now=1e9)
    assert 'data-state="disconnected"' in html and "DISCONNECTED · feed no data" in html
    row = L.Row(
        event="E1",
        strike=1,
        outcome=1,
        ts=1e9,
        p=0.6,
        conf=0.1,
        jev_p=0.6,
        jev_conf=0.5,
        jev_choice="up",
    )
    lg = L.build([row])
    ok = render(lg, start="x", now=1e9 + 30)
    assert 'data-state="connected"' in ok
    down = render(lg, start="x", now=1e9 + 30, supervisor_down=True)
    assert "DISCONNECTED · worker supervisor down" in down


def test_order_ticket_is_scoped_to_grants(client):
    c = client("laya", "coin")
    order = {"path": "broadcast", "side": "YES", "notional": "5"}
    denied = c.post("/demo/api/orders", json={**order, "accounts": ["laya", "jev"]})
    assert denied.status_code == 403  # an ungranted leg fails the whole ticket, nothing journaled
    ok = c.post("/demo/api/orders", json={**order, "accounts": ["laya", "coin"]})
    assert ok.status_code == 200 and ok.json()["state"] == "sent"
    client("laya", "jev", "coin").post("/demo/api/orders", json={**order, "accounts": ["jev"]})
    body = client("laya", "coin").get("/demo/api/orders").json()
    assert {o["account"] for o in body["orders"] if o["source"] == "ticket"} == {"laya", "coin"}
    assert len(body["parents"]) == 1  # the jev-only parent never reaches this caller
    assert 'value="jev"' not in client("laya", "coin").get("/demo").text
