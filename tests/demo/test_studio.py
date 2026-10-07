"""ALG-3256 strategy studio: frozen versions, fan-out preview arithmetic, skips."""

from decimal import Decimal

import pytest

from algobots.demo import studio as S
from algobots.strategies import dsl

D = Decimal


def _st(tmp_path) -> S.Studio:
    return S.load(str(tmp_path))


def test_builtin_catalogue_has_three_test_templates_and_three_live():
    st = S.load("/nonexistent")
    tests = [v for v in st.versions if S.DEFINITIONS[v.definition].label == S.TEST_LABEL]
    live = [v for v in st.versions if S.DEFINITIONS[v.definition].kind == "live"]
    assert {v.definition for v in tests} == {"trend", "range_rsi", "etf_alloc"}
    assert {v.definition for v in live} == {"laya", "jev", "coin"}
    assert len({v.hash for v in st.versions}) == 6


def test_dsl_templates_hash_through_dsl_and_change_with_params():
    v1 = S.freeze("trend", {}, 1)
    v2 = S.freeze("trend", {"fast": 10, "slow": 30}, 2)
    assert v1.spec_hash == dsl.artifact_hash(S.TrendParams().spec())
    assert v1.hash != v2.hash and v1.spec_hash != v2.spec_hash
    assert S.freeze("trend", {"slow": 50, "fast": 20}, 9).hash == v1.hash  # key order irrelevant


@pytest.mark.parametrize(
    "definition,params,msg",
    [
        ("trend", {"fast": 50, "slow": 20}, r"fast \(50\) must be below slow"),
        ("trend", {"fast": 10, "lookback": 3}, "Extra inputs"),
        ("range_rsi", {"lower": 80, "upper": 20}, r"lower \(80.0\) must be below"),
        ("etf_alloc", {"weights": {"SPY": 0.5, "AGG": 0.4}}, "not 1"),
    ],
)
def test_typed_params_reject_bad_input(definition, params, msg):
    with pytest.raises(S.StudioError, match=msg):
        S.freeze(definition, params, 2)


def test_equal_dollar_split_rounds_down_and_reports_residuals(tmp_path):
    st = _st(tmp_path)
    v = st.latest("trend")
    pv = S.preview(st, v, ["eq-a", "eq-b", "eq-c"], mode="equal", amount=D("1000"))
    a, b, c = pv.lines
    assert [ln.allocation for ln in pv.lines] == [D("333.33")] * 3
    assert (a.residual, b.residual, c.residual) == (D("666.67"), D("2166.67"), D("166.67"))
    assert pv.allocated == D("999.99") and pv.undeployed == D("0.01")


def test_equal_dollar_caps_at_headroom_without_redistributing(tmp_path):
    st = _st(tmp_path)
    pv = S.preview(st, st.latest("trend"), ["eq-b", "eq-c"], mode="equal", amount=D("2000"))
    b, c = pv.lines
    assert b.allocation == D("1000.00") and b.residual == D("1500")
    assert c.allocation == D("500") and c.residual == 0  # capped at its 500 approval
    assert pv.undeployed == D("500.00")


def test_percent_of_approved_allocation(tmp_path):
    st = _st(tmp_path)
    pv = S.preview(st, st.latest("etf_alloc"), ["eq-a", "eq-b"], mode="pct", pct=D("25"))
    assert [ln.allocation for ln in pv.lines] == [D("250.00"), D("625.00")]
    assert pv.requested == D("875.00") and pv.undeployed == 0


def test_skips_carry_explicit_reasons(tmp_path):
    st = _st(tmp_path)
    v = st.latest("range_rsi")
    pv = S.preview(st, v, ["laya", "eq-c", "nope", "eq-a"], mode="pct", pct=D("10"))
    why = {ln.account: ln.skip for ln in pv.lines}
    assert why["laya"] == "equities strategy cannot trade on a kalshi account"
    assert why["nope"] == "unknown account"
    assert why["eq-c"] == "50.00 USD is below the 100 USD minimum"
    assert why["eq-a"] is None and pv.allocated == D("100.00")
    assert all(ln.allocation == 0 for ln in pv.lines if ln.skip)

    killed = S.preview(st, v, ["eq-a"], mode="equal", amount=D("500"), kill_engaged=True)
    assert killed.lines[0].skip.startswith("kill switch engaged")
    assert killed.undeployed == D("500")

    live = S.preview(st, st.latest("laya"), ["laya"], mode="equal", amount=D("100"))
    assert "pinned to its own sleeve" in live.lines[0].skip


def test_skips_duplicate_version_and_exhausted_headroom(tmp_path):
    sd = str(tmp_path)
    v = S.load(sd).latest("trend")
    S.deploy(sd, v.hash, ["eq-c"], mode="pct", pct=D("100"), actor="t")
    st = S.load(sd)
    dup = S.preview(st, v, ["eq-c"], mode="equal", amount=D("100")).lines[0]
    assert dup.skip == f"version {v.short} already deployed here (dep-{v.hash[:8]}-eq-c)"
    other = S.preview(st, st.latest("range_rsi"), ["eq-c"], mode="equal", amount=D("100"))
    assert other.lines[0].skip == "no headroom: 500.00 of 500 USD already committed"


def test_invalid_sizing_rejected(tmp_path):
    st = _st(tmp_path)
    v = st.latest("trend")
    with pytest.raises(S.StudioError, match="above 0"):
        S.preview(st, v, ["eq-a"], mode="equal", amount=D("0"))
    with pytest.raises(S.StudioError, match=r"\(0, 100\]"):
        S.preview(st, v, ["eq-a"], mode="pct", pct=D("120"))
    with pytest.raises(S.StudioError, match="at least one"):
        S.preview(st, v, [], mode="pct", pct=D("10"))


def test_edit_never_changes_running_deployment(tmp_path):
    sd = str(tmp_path)
    v1 = S.load(sd).latest("trend")
    _, (dep,), _ = S.deploy(sd, v1.hash, ["eq-a"], mode="equal", amount=D("400"), actor="pat")
    v2 = S.edit(sd, "trend", {"fast": 5, "slow": 15}, actor="pat")
    assert v2.version == 2 and v2.hash != v1.hash
    st = S.load(sd)
    (kept,) = [d for d in st.deployments if d.id == dep.id]
    assert kept.hash == v1.hash and kept.params == v1.params and kept.params["fast"] == 20
    assert st.latest("trend").hash == v2.hash
    assert S.edit(sd, "trend", {"fast": 5, "slow": 15}, actor="pat").version == 2  # no-op


def test_three_template_instances_stay_attributable(tmp_path):
    sd = str(tmp_path)
    S.edit(sd, "trend", {"fast": 10, "slow": 30}, actor="pat")
    st = S.load(sd)
    trend1 = next(v for v in st.versions if v.definition == "trend" and v.version == 1)
    trend2 = st.latest("trend")
    rsi = st.latest("range_rsi")
    S.deploy(sd, trend1.hash, ["eq-a"], mode="equal", amount=D("300"), actor="pat")
    S.deploy(sd, trend2.hash, ["eq-b"], mode="equal", amount=D("300"), actor="pat")
    S.deploy(sd, rsi.hash, ["eq-a"], mode="equal", amount=D("300"), actor="pat")
    deps = [d for d in S.load(sd).deployments if d.state == "pending"]
    assert len(deps) == 3 and len({d.id for d in deps}) == 3 and len({d.hash for d in deps}) == 3
    assert {(d.account, d.definition, d.version) for d in deps} == {
        ("eq-a", "trend", 1),
        ("eq-b", "trend", 2),
        ("eq-a", "range_rsi", 1),
    }
    assert S.load(sd).committed("eq-a") == D("600.00")


# --- routes ----------------------------------------------------------------------


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


def test_studio_routes_preview_deploy_edit_and_attribute(demo):
    client, sd = demo
    v = S.load(sd).latest("trend")
    q = {"version": v.short, "accounts": ["eq-a", "laya"], "mode": "equal", "amount": "600"}
    page = client.get("/demo/studio", params=q).text
    assert S.TEST_LABEL in page and "Create 1 paper deployment" in page
    assert "equities strategy cannot trade on a kalshi account" in page

    pv = client.get("/demo/api/studio/preview", params=q).json()
    assert pv["allocated"] == "600.00" and pv["undeployed"] == "0.00"  # split over eligible only
    assert client.get("/demo/api/studio/preview", params={**q, "amount": "x"}).status_code == 422

    r = client.post("/demo/studio/deploy", data={**q, "actor": "pat"}, follow_redirects=False)
    assert (
        r.status_code == 303 and f"dep-{v.hash[:8]}-eq-a" in client.get(r.headers["location"]).text
    )

    r = client.post(
        "/demo/studio/edit",
        data={
            "definition": "trend",
            "p_fast": "8",
            "p_slow": "21",
            "p_symbol": "SPY",
            "p_cadence": "1d",
        },
        follow_redirects=False,
    )
    assert "v2" in client.get(r.headers["location"]).text
    bad = client.post(
        "/demo/studio/edit", data={"definition": "trend", "p_fast": "50", "p_slow": "8"}
    )
    assert "Edit refused" in bad.text and 'role="alert"' in bad.text

    api = client.get("/demo/api/strategies").json()
    (dep,) = [d for d in api["deployments"] if d["state"] == "pending"]
    assert dep["hash"] == v.hash and dep["params"]["fast"] == 20  # v2 edit did not reach it
    home = client.get("/demo?view=accounts").text
    assert dep["id"] in home and "Strategies" in home


def test_orders_carry_live_deployment_attribution():
    from tests.demo.test_ledger import _row

    from algobots.demo import blotter as B
    from algobots.demo import ledger as L

    lg = L.build([_row(i, 0.6, 1) for i in range(3)])
    orders = B.orders(lg)
    assert {o["deployment"] for o in orders} == {"dep-laya-live", "dep-jev-live", "dep-coin-live"}
    laya = next(v for v in S.BUILTIN if v.definition == "laya")
    assert all(o["artifact"] == laya.short for o in orders if o["account"] == "laya")


def test_studio_respects_account_scope(demo):
    from tests.demo.test_scope import _scope

    from algobots.api.main import app
    from algobots.demo.scope import current_scope

    client, sd = demo
    app.dependency_overrides[current_scope] = lambda: _scope("laya")
    try:
        v = S.load(sd).latest("trend")
        q = {"version": v.short, "accounts": ["jev", "eq-a"], "mode": "equal", "amount": "200"}
        pv = client.get("/demo/api/studio/preview", params=q).json()
        assert pv["lines"][0]["skip"] == "unknown account" and pv["lines"][0]["label"] == "jev"
        page = client.get("/demo/studio").text
        assert "Jev zero-shot" not in page and "Laya System One" in page
        api = client.get("/demo/api/strategies").json()
        assert {d["account"] for d in api["deployments"]} == {"laya"}
        app.dependency_overrides[current_scope] = lambda: _scope()
        assert client.get("/demo/studio").status_code == 403
    finally:
        app.dependency_overrides.pop(current_scope, None)
