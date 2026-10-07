"""ALG-3282 (A11-3): instrument ownership, fan-out campaigns with per-account
children, derived parent state, risk-rejected children, recovery (disable a
version, pause a campaign) — and the JSON/HTML surfaces that expose them."""

from decimal import Decimal

import pytest

from algobots.demo import studio as S
from algobots.engine.workers import template as T

D = Decimal
T0 = 1_790_000_000.0  # deploy time
SIX_H = T0 + 6 * 3600
DAY = T0 + 86400


def _fast(sd, symbol="SPY", **kw):
    """A 1m-cadence trend version so entries/exits fire within hours."""
    return S.edit(
        sd,
        "trend",
        {"cadence": "1m", "fast": 3, "slow": 8, "symbol": symbol, **kw},
        actor="t",
        now=T0,
    )


def _run(dep, sd, *steps):
    r = T.TemplateRunner(dep, sd)
    r.reconcile()
    return r, [o for now in steps for o in r.step(now)]


def _dep(st, account, definition="trend"):
    return next(d for d in st.deployments if d.account == account and d.definition == definition)


# --- instrument ownership (AC4) ------------------------------------------------------


def test_conflicting_instrument_is_rejected_naming_the_owner(tmp_path):
    sd = str(tmp_path)
    v1 = S.load(sd).latest("trend")  # builtin v1, trades SPY
    S.deploy(sd, v1.hash, ["eq-a"], mode="equal", amount=D("300"), actor="t", now=T0)
    st = S.load(sd)
    v2 = S.edit(sd, "range_rsi", {"cadence": "1m", "symbol": "SPY"}, actor="t", now=T0)

    other = S.preview(st, v2, ["eq-a"], mode="equal", amount=D("200")).lines[0]
    assert other.skip == f"SPY on eq-a is owned by Trend crossover v1 (dep-{v1.hash[:8]}-eq-a)"

    pv, made, cmp = S.deploy(
        sd, v2.hash, ["eq-a"], mode="equal", amount=D("200"), actor="t", now=T0
    )
    assert not made and pv.allocated == 0
    assert [(c.status, c.reason) for c in cmp.children] == [("skipped", other.skip)]

    # a different instrument on the same account, and the same instrument on
    # another account, are both still free: ownership is per (account, instrument)
    qqq = S.edit(sd, "range_rsi", {"cadence": "1m", "symbol": "QQQ"}, actor="t", now=T0)
    assert S.preview(st, qqq, ["eq-a"], mode="equal", amount=D("200")).lines[0].skip is None
    assert S.preview(st, v2, ["eq-b"], mode="equal", amount=D("200")).lines[0].skip is None


def test_etf_weights_count_as_owned_instruments(tmp_path):
    sd = str(tmp_path)
    v = _fast(sd, symbol="SPY")
    S.deploy(sd, v.hash, ["eq-a"], mode="equal", amount=D("300"), actor="t", now=T0)
    alloc = S.load(sd).latest("etf_alloc")
    line = S.preview(S.load(sd), alloc, ["eq-a"], mode="pct", pct=D("10")).lines[0]
    assert line.skip is not None and line.skip.startswith("SPY on eq-a is owned by")


def test_pending_deployment_owns_until_it_stops(tmp_path):
    sd = str(tmp_path)
    v1 = _fast(sd)
    S.deploy(sd, v1.hash, ["eq-a"], mode="equal", amount=D("300"), actor="t", now=T0)
    st = S.load(sd)
    assert (dep := _dep(st, "eq-a")).state == "pending"
    assert ("eq-a", "SPY") in S.owners(st)
    S.set_state(sd, dep.id, "running")
    assert ("eq-a", "SPY") in S.owners(S.load(sd))  # still active: still owns


# --- fan-out campaigns (AC3, AC5) ----------------------------------------------------


def test_four_accounts_one_ineligible_fan_out_three_children_and_a_skip(tmp_path):
    sd = str(tmp_path)
    v = _fast(sd, symbol="QQQ")
    st = S.load(sd)
    pv = S.preview(st, v, ["eq-a", "eq-b", "eq-c", "laya"], mode="equal", amount=D("900"))
    assert [ln.skip is None for ln in pv.lines] == [True, True, True, False]

    pv, made, cmp = S.deploy(
        sd,
        v.hash,
        ["eq-a", "eq-b", "eq-c", "laya"],
        mode="equal",
        amount=D("900"),
        actor="t",
        now=T0,
    )
    assert cmp.id == f"cmp-{v.hash[:8]}-1" and len(cmp.children) == 4
    assert len(made) == 3 and len({d.id for d in made}) == 3  # three independent children
    kids = {c.account: c for c in cmp.children}
    assert {a: kids[a].status for a in ("eq-a", "eq-b", "eq-c")} == {
        a: "pending" for a in ("eq-a", "eq-b", "eq-c")
    }
    assert kids["laya"].status == "skipped"
    assert kids["laya"].reason == "equities strategy cannot trade on a kalshi account"
    assert kids["laya"].deployment is None
    assert all(kids[a].deployment for a in ("eq-a", "eq-b", "eq-c"))


def test_child_rejected_by_risk_carries_the_denial_reason(tmp_path):
    sd = str(tmp_path)
    v = _fast(sd, symbol="QQQ")
    pv, made, cmp = S.deploy(
        sd, v.hash, ["eq-a", "eq-b"], mode="pct", pct=D("100"), actor="t", now=T0
    )
    eq_a, eq_b = cmp.children
    assert eq_a.status == "pending" and eq_a.allocation == "1000.00"
    assert eq_b.status == "rejected-by-risk" and eq_b.deployment is None
    assert eq_b.reason == (
        "blocked by risk gate — 2500.00 USD over max order value; "
        "gate allows 1000 USD per deployment"
    )
    assert [d.account for d in made] == ["eq-a"]  # the rejected child never deployed
    assert eq_b in cmp.children  # ...but the campaign records it


def test_two_of_four_succeed_is_partial_and_the_fills_stay(tmp_path):
    sd = str(tmp_path)
    v = _fast(sd, symbol="QQQ")
    _, _, cmp = S.deploy(
        sd, v.hash, ["eq-a", "eq-b", "eq-c", "laya"], mode="pct", pct=D("100"), actor="t", now=T0
    )
    st = S.load(sd)
    for account in ("eq-a", "eq-c"):
        _, orders = _run(_dep(st, account), sd, SIX_H)
        assert orders and all(o["status"] == "filled" for o in orders)

    log = T.load_orders(sd)
    states = {c.account: S.child_view(c, st, log) for c in cmp.children}
    assert [states[a][0] for a in ("eq-a", "eq-c")] == ["filled", "filled"]
    assert states["eq-b"][0] == "rejected-by-risk"
    assert states["laya"][0] == "skipped"

    state, ok, n = S.campaign_state(cmp, [s for s, _ in states.values()])
    assert (state, ok, n) == ("partial", 2, 4)
    assert S.campaign_display(cmp, [s for s, _ in states.values()]) == "PARTIAL · 2/4"
    assert state != "succeeded"  # never claims success with a failed child

    # no cross-account atomicity: eq-b's rejection reversed nothing on eq-a/eq-c
    for account in ("eq-a", "eq-c"):
        dep = _dep(st, account)
        log = T.read_log(T.orders_path(sd, dep.id))
        book = T.book(dep, log)
        filled = sum(1 for o in log if o["status"] == "filled")
        assert book.filled == filled  # the fills remain in place


def test_a_failing_child_never_reverses_its_siblings(tmp_path):
    sd = str(tmp_path)
    v = _fast(sd, symbol="QQQ")
    _, _, cmp = S.deploy(sd, v.hash, ["eq-a", "eq-b"], mode="pct", pct=D("100"), actor="t", now=T0)
    st = S.load(sd)
    _, before = _run(_dep(st, "eq-a"), sd, SIX_H)
    assert before
    # eq-b's child was rejected at deploy — eq-a's log is untouched by it
    assert all(o["account"] == "eq-a" for o in T.load_orders(sd))
    assert len(T.read_log(T.orders_path(sd, _dep(st, "eq-a").id))) == len(before)


@pytest.mark.parametrize(
    "states,expected",
    [
        (["filled", "filled"], ("succeeded", 2, 2)),
        (["filled", "rejected-by-risk"], ("partial", 1, 2)),
        (["filled", "skipped"], ("partial", 1, 2)),
        (["skipped", "skipped"], ("rejected", 0, 2)),
        (["filled", "pending"], ("running", 1, 2)),
        (["running", "running"], ("running", 0, 2)),
        (["pending", "pending"], ("running", 0, 2)),
        (["filled", "partially-filled"], ("running", 1, 2)),
        (["partially-filled", "rejected-by-risk"], ("running", 0, 2)),
    ],
)
def test_parent_state_is_derived_and_strict(states, expected):
    cmp = S.Campaign("cmp-x", "h", "trend", "equal", "100", 0.0, "t")
    assert S.campaign_state(cmp, states) == expected


def test_partially_filled_child_blocks_a_succeeded_parent(tmp_path):
    sd = str(tmp_path)
    v = _fast(sd, symbol="QQQ")
    _, (dep_a,), cmp = S.deploy(
        sd, v.hash, ["eq-a"], mode="equal", amount=D("300"), actor="t", now=T0
    )
    S.deploy(sd, v.hash, ["eq-c"], mode="equal", amount=D("300"), actor="t", now=T0)  # sibling cmp
    st = S.load(sd)
    r, _ = _run(dep_a, sd, SIX_H)
    r.step(SIX_H + 3600, killed=True)  # later entries blocked by the kill switch
    log = T.load_orders(sd)
    (eq_a,) = cmp.children
    state, why = S.child_view(eq_a, st, log)
    assert state == "partially-filled" and "blocked" in why


# --- recovery: disable a version, pause a campaign -----------------------------------


def test_disabled_version_keeps_deployments_and_history(tmp_path):
    sd = str(tmp_path)
    v1 = _fast(sd)
    _, (dep,), _ = S.deploy(sd, v1.hash, ["eq-a"], mode="equal", amount=D("300"), actor="t", now=T0)
    flagged = S.set_disabled(sd, v1.hash, disabled=True, actor="pat", now=T0 + 10)
    assert flagged.disabled and flagged.hash == v1.hash

    st = S.load(sd)
    assert st.by_hash(v1.hash).disabled
    line = S.preview(st, st.by_hash(v1.hash), ["eq-b"], mode="equal", amount=D("200")).lines[0]
    assert line.skip == f"version {v1.short} is disabled for new deployments (by pat)"
    _, made, cmp = S.deploy(sd, v1.hash, ["eq-b"], mode="equal", amount=D("200"), actor="t")
    assert not made and [c.status for c in cmp.children] == ["skipped"]

    # history and running deployments survive the flag
    st = S.load(sd)
    assert any(x.hash == v1.hash for x in st.versions) and any(
        d.id == dep.id for d in st.deployments
    )
    _, orders = _run(dep, sd, SIX_H)
    assert orders  # the existing deployment keeps trading its frozen copy

    again = S.set_disabled(sd, v1.hash, disabled=False, actor="pat")
    assert not again.disabled
    assert S.preview(S.load(sd), v1, ["eq-b"], mode="equal", amount=D("200")).lines[0].skip is None


def test_paused_campaign_holds_entries_and_keeps_protective_orders(tmp_path):
    sd = str(tmp_path)
    v = _fast(sd)
    _, (dep,), cmp = S.deploy(
        sd, v.hash, ["eq-a"], mode="equal", amount=D("300"), actor="t", now=T0
    )
    r, before = _run(dep, sd, SIX_H)
    assert any(o["side"] == "BUY" and o["status"] == "filled" for o in before)  # holds a position

    paused = S.pause_campaign(sd, cmp.id, paused=True, actor="pat", now=SIX_H)
    assert paused.paused and paused.paused_by == "pat"
    after = r.step(DAY)
    buys = [o for o in after if o["side"] == "BUY"]
    assert buys and all(
        o["status"] == "blocked" and "campaign paused by pat" in o["reason"] for o in buys
    )
    # already-placed protective orders are left in place: exits still fill
    sells = [o for o in after if o["side"] == "SELL"]
    assert all(o["status"] == "filled" for o in sells)
    # the pre-pause history is untouched
    log = T.read_log(T.orders_path(sd, dep.id))
    assert [o["id"] for o in log[: len(before)]] == [o["id"] for o in before]

    resumed = S.pause_campaign(sd, cmp.id, paused=False, actor="pat", now=DAY)
    assert not resumed.paused
    more = r.step(DAY + 6 * 3600)
    assert any(o["side"] == "BUY" and o["status"] == "filled" for o in more)  # entries are back


def test_unknown_campaign_and_version_refused(tmp_path):
    sd = str(tmp_path)
    with pytest.raises(S.StudioError, match="unknown campaign"):
        S.pause_campaign(sd, "cmp-nope", paused=True, actor="t")
    with pytest.raises(S.StudioError, match="unknown strategy version"):
        S.set_disabled(sd, "deadbeef", disabled=True, actor="t")


# --- routes: page + JSON ------------------------------------------------------------


@pytest.fixture
def demo(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from algobots.api.config import get_settings
    from algobots.api.main import app

    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(tmp_path / "none.jsonl"))
    get_settings.cache_clear()
    yield TestClient(app), str(tmp_path)
    get_settings.cache_clear()


def _partial_campaign(sd):
    """One campaign over four accounts: eq-a+eq-c fill, eq-b is risk-rejected,
    laya is skipped -> PARTIAL · 2/4 with the fills still in place."""
    v = _fast(sd, symbol="QQQ")
    _, _, cmp = S.deploy(
        sd, v.hash, ["eq-a", "eq-b", "eq-c", "laya"], mode="pct", pct=D("100"), actor="pat", now=T0
    )
    st = S.load(sd)
    for account in ("eq-a", "eq-c"):
        _run(_dep(st, account), sd, SIX_H)
    return cmp


def test_studio_page_shows_campaign_children_and_partial_status(demo):
    client, sd = demo
    cmp = _partial_campaign(sd)
    page = client.get("/demo/studio", params={"campaign": cmp.id}).text
    assert "PARTIAL · 2/4" in page
    assert cmp.id in page
    assert "REJECTED BY RISK" in page and "over max order value" in page
    assert "SKIPPED" in page and "cannot trade on a kalshi account" in page
    assert "Order timeline" in page and "data-order-id" in page
    assert 'data-environment="PAPER"' in page  # per-deployment paper badge
    assert f'action="/demo/studio/campaign/{cmp.id}/pause"' in page


def test_campaigns_json_exposes_children_and_timelines(demo):
    client, sd = demo
    cmp = _partial_campaign(sd)
    api = client.get("/demo/api/campaigns").json()
    (got,) = [c for c in api["campaigns"] if c["id"] == cmp.id]
    assert got["display"] == "PARTIAL · 2/4" and got["status"] == "partial"
    assert got["strategy"] == "Trend crossover" and got["requested"] == "4000.00"
    kids = {k["account"]: k for k in got["children"]}
    assert kids["eq-a"]["status"] == "filled" and kids["eq-a"]["deployment"]
    assert kids["eq-b"]["status"] == "rejected-by-risk"
    assert "over max order value" in kids["eq-b"]["reason"]
    assert kids["laya"]["status"] == "skipped"
    assert got["timeline"] and all(
        k in got["timeline"][0] for k in ("ts", "instrument", "side", "status", "reason")
    )
    assert {o["account"] for o in got["timeline"]} <= {"eq-a", "eq-c"}


def test_pause_and_disable_routes_round_trip(demo):
    client, sd = demo
    cmp = _partial_campaign(sd)
    v = S.load(sd).latest("trend")

    r = client.post(
        f"/demo/studio/campaign/{cmp.id}/pause", data={"paused": "on"}, follow_redirects=False
    )
    page = client.get(r.headers["location"]).text
    assert "paused — new entries held" in page and "RESUME" not in page
    assert S.load(sd).campaigns[0].paused

    r = client.post(
        "/demo/studio/disable",
        data={"version": v.short, "disable": "on"},
        follow_redirects=False,
    )
    page = client.get(r.headers["location"]).text
    assert "disabled for new deployments" in page
    assert S.load(sd).by_hash(v.hash).disabled

    r = client.post(
        "/demo/studio/disable", data={"version": v.short, "disable": "off"}, follow_redirects=False
    )
    assert not S.load(sd).by_hash(v.hash).disabled


def test_campaigns_follow_the_studio_scope_model(demo):
    from tests.demo.test_scope import _scope

    from algobots.api.main import app
    from algobots.demo.scope import current_scope

    client, sd = demo
    cmp = _partial_campaign(sd)
    # no grant at all -> 403, same as every studio view
    app.dependency_overrides[current_scope] = lambda: _scope()
    try:
        assert client.get("/demo/api/campaigns").status_code == 403
        # a granted sleeve sees the campaign; the equity paper accounts are
        # visible to every ACCOUNT_READ holder (the standing studio model)
        app.dependency_overrides[current_scope] = lambda: _scope("laya")
        api = client.get("/demo/api/campaigns").json()
        (got,) = api["campaigns"]
        assert got["id"] == cmp.id
        assert {k["account"] for k in got["children"]} == {"eq-a", "eq-b", "eq-c", "laya"}
        assert got["timeline"] and {o["account"] for o in got["timeline"]} == {"eq-a", "eq-c"}
    finally:
        app.dependency_overrides.pop(current_scope, None)
