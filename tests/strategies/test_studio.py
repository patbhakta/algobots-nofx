"""ALG-3408: Studio draft contract, compiler, and the NoFX save path through it."""

import copy

import pytest
from fastapi.testclient import TestClient

from algobots.strategies.dsl import SPEC_KIND
from algobots.strategies.studio import (
    IMPLEMENTATIONS,
    StudioError,
    compile_studio_strategy,
    parse_draft,
    translate_nofx_config,
)
from tests.conftest import TEST_PASSWORD

SMA_CROSS = {
    "left": {"indicator": "sma", "params": {"period": 20}},
    "op": "crosses_above",
    "right": {"indicator": "sma", "params": {"period": 50}},
}
SMA_UNCROSS = {**SMA_CROSS, "op": "crosses_below"}

DRAFT = {
    "schema_version": 1,
    "name": "US momentum careful",
    "universe": {"asset_class": "equity", "symbols": ["AAPL.XNAS"], "datafeed": "ibkr"},
    "signals": {
        "cadence": "15m",
        "bars": 50,
        "indicators": [{"kind": "ema", "period": 20}, {"kind": "rsi", "period": 14}],
        "entry": {"all": [SMA_CROSS]},
        "exit": SMA_UNCROSS,
    },
    "decision": {"mode": "deterministic"},
    "risk": {"max_positions": 1, "max_order_value": "1000.00", "max_daily_loss": "100.00"},
}

NOFX_MOMENTUM = {
    "strategy_type": "ai_trading",
    "ai_config": {
        "coin_source": {"source_type": "static", "static_coins": ["KXBTC15M"]},
        "indicators": {"klines": {"primary_timeframe": "15m", "primary_count": 20}},
        "custom_prompt": "Kalshi BTC 15m momentum. Paper only.",
        "risk_control": {"max_positions": 1, "btc_eth_max_leverage": 5},
        "nofxos_api_key": "should-never-survive",
    },
    "demo_worker": {"min_edge": 0.05, "max_order_value": "5.00", "max_daily_loss": "20.00"},
}


def _d(**overrides):
    d = copy.deepcopy(DRAFT)
    for path, value in overrides.items():
        node = d
        *head, last = path.split("__")
        for k in head:
            node = node[k]
        node[last] = value
    return d


# --- contract ---


@pytest.mark.parametrize(
    ("draft", "field"),
    [
        (_d(extra_key=1), "extra_key"),
        (_d(risk__max_order_value=1000.0), "risk.max_order_value"),  # floats for money
        (_d(universe__symbols=["AAPL"]), "universe.symbols.0"),  # not a Nautilus id
        (_d(universe__module="os"), "universe.module"),
        (_d(decision__custom_prompt="buy"), "decision"),  # prompt outside prompt mode
    ],
)
def test_draft_is_strict(draft, field):
    with pytest.raises(StudioError) as exc:
        parse_draft(draft)
    assert exc.value.field == field


def test_schema_version_is_mandatory():
    d = _d()
    del d["schema_version"]
    with pytest.raises(StudioError) as exc:
        parse_draft(d)
    assert exc.value.field == "schema_version"


# --- compiler ---


def test_compile_is_deterministic_and_allowlisted():
    a = compile_studio_strategy(parse_draft(_d()))
    b = compile_studio_strategy(parse_draft(_d()))
    assert a.artifact_hash == b.artifact_hash and len(a.artifact_hash) == 64
    assert a.implementation == "condition_dsl.v1" and a.implementation in IMPLEMENTATIONS
    assert a.nautilus["bar_types"] == ["AAPL.XNAS-15-MINUTE-LAST-EXTERNAL"]
    assert a.nautilus["warmup_bars"] == 51  # crosses need period + 1 > bars=50
    assert a.spec["warmup_bars"] == 51
    c = compile_studio_strategy(parse_draft(_d(risk__max_daily_loss="99.00")))
    assert c.artifact_hash != a.artifact_hash


def test_artifact_has_no_code_paths():
    art = compile_studio_strategy(parse_draft(_d())).model_dump_json()
    for needle in ("import", "module", "class_path", "http"):
        assert needle not in art


@pytest.mark.parametrize(
    ("draft", "field"),
    [
        (_d(risk__max_order_value=None), "risk.max_order_value"),
        (_d(decision={"mode": "prompt", "custom_prompt": "x"}), "decision.mode"),
        (_d(signals__entry={"all": []}, signals__exit={"all": []}), "signals.entry"),
        (_d(signals__entry={"left": {"indicator": "macd"}}), "signals"),
    ],
)
def test_compile_errors_name_the_owning_field(draft, field):
    with pytest.raises(StudioError) as exc:
        compile_studio_strategy(parse_draft(draft))
    assert exc.value.field == field


def test_nofx_momentum_translates_and_compiles_to_kalshi_momentum():
    draft, warnings = translate_nofx_config("Kalshi BTC 15m momentum", NOFX_MOMENTUM)
    assert draft["universe"] == {
        "asset_class": "prediction",
        "symbols": ["KXBTC15M.KALSHI"],
        "datafeed": "kalshi",
    }
    assert "should-never-survive" not in str(draft)
    assert any("nofxos_api_key" in w for w in warnings)
    assert any("leverage" in w for w in warnings)
    art = compile_studio_strategy(parse_draft(draft))
    assert art.implementation == "kalshi_momentum.v1"
    assert art.nautilus["params"] == {"p_source": "mom3x15m/vol20", "min_edge": 0.05}
    assert art.nautilus["risk_envelope"]["max_order_value"] == "5.00"


@pytest.mark.parametrize(
    ("config", "field"),
    [
        ({"grid_config": {"levels": 5}}, "grid_config"),
        ({"ai_config": {"coin_source": {"static_coins": ["BTCUSDT"]}}}, "coin_source.static_coins"),
        ({"ai_config": {"coin_source": {"source_type": "ai500"}}}, "coin_source.source_type"),
    ],
)
def test_nofx_translation_refuses_explicitly(config, field):
    with pytest.raises(StudioError) as exc:
        translate_nofx_config("x", config)
    assert exc.value.field == field


# --- routes ---


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def token(client: TestClient, founder: dict) -> str:
    r = client.post("/api/nofx/login", json={"email": founder["email"], "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_draft_save_patch_compile_deploy(client, token):
    r = client.post("/api/studio/strategies", json=_d(), headers=_h(token))
    assert r.status_code == 201, r.text
    draft = r.json()
    assert draft["revision"] == 1 and draft["artifacts"] == []

    bad = client.post("/api/studio/strategies", json=_d(extra=1), headers=_h(token))
    assert bad.status_code == 422 and bad.json()["detail"]["field"] == "extra"

    url = f"/api/studio/strategies/{draft['id']}"
    stale = client.patch(url, json={"revision": 2, "draft": _d()}, headers=_h(token))
    assert stale.status_code == 409
    ok = client.patch(url, json={"revision": 1, "draft": _d(name="v2")}, headers=_h(token))
    assert ok.status_code == 200 and ok.json()["revision"] == 2

    c1 = client.post(f"{url}/compile", headers=_h(token))
    assert c1.status_code == 201, c1.text
    art = c1.json()
    assert art["deployable"] and art["draft_revision"] == 2
    again = client.post(f"{url}/compile", headers=_h(token))
    assert again.status_code == 200 and again.json()["strategy_id"] == art["strategy_id"]

    # the compiled row is an ordinary condition_dsl strategy: deployable unchanged
    compiled = client.get(f"/api/strategies/{art['strategy_id']}", headers=_h(token))
    assert compiled.status_code == 200 and compiled.json()["kind"] == SPEC_KIND
    acct = client.post(
        "/api/accounts", headers=_h(token), json={"label": "Studio", "broker": "alpaca"}
    ).json()
    dep = client.post(
        "/api/deployments",
        headers=_h(token),
        json={
            "strategy_id": art["strategy_id"],
            "account_id": acct["id"],
            "symbol": "AAPL",
            "max_order_value": art["nautilus"]["risk_envelope"]["max_order_value"],
            "max_daily_loss": art["nautilus"]["risk_envelope"]["max_daily_loss"],
        },
    )
    assert dep.status_code == 201, dep.text
    assert dep.json()["frozen_spec"]["spec"] == art["spec"]

    # edits after compile append; the earlier artifact is untouched
    client.patch(url, json={"revision": 2, "draft": _d(name="v3")}, headers=_h(token))
    c2 = client.post(f"{url}/compile", headers=_h(token)).json()
    assert c2["artifact_hash"] != art["artifact_hash"]
    arts = client.get(url, headers=_h(token)).json()["artifacts"]
    assert [a["artifact_hash"] for a in arts] == [art["artifact_hash"], c2["artifact_hash"]]


def test_drafts_are_tenant_scoped(client, token):
    r = client.post("/api/studio/strategies", json=_d(), headers=_h(token))
    assert client.get(f"/api/studio/strategies/{r.json()['id']}").status_code == 401
    assert client.get("/api/studio/strategies/not-a-uuid", headers=_h(token)).status_code == 404


def test_nofx_save_goes_through_studio_contract(client, token):
    r = client.post(
        "/api/nofx/strategies",
        json={"name": "Kalshi momentum", "config": NOFX_MOMENTUM},
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    studio = r.json()["studio"]
    assert studio["status"] == "compiled" and studio["implementation"] == "kalshi_momentum.v1"
    draft = client.get(f"/api/studio/strategies/{studio['draft_id']}", headers=_h(token)).json()
    assert draft["artifacts"][0]["artifact_hash"] == studio["artifact_hash"]

    # editing in NoFX revises the same draft and compiles a new artifact
    cfg = copy.deepcopy(NOFX_MOMENTUM)
    cfg["demo_worker"]["min_edge"] = 0.08
    put = client.put(
        f"/api/nofx/strategies/{r.json()['id']}",
        json={"name": "Kalshi momentum", "config": cfg},
        headers=_h(token),
    ).json()["studio"]
    assert put["draft_id"] == studio["draft_id"] and put["revision"] == 2
    assert put["artifact_hash"] != studio["artifact_hash"]

    # an untranslatable config still saves in NoFX, with the owning field named
    bad = client.post(
        "/api/nofx/strategies",
        json={"name": "grid", "config": {"grid_config": {"levels": 3}}},
        headers=_h(token),
    ).json()["studio"]
    assert bad == {
        "status": "invalid",
        "draft_id": None,
        "field": "grid_config",
        "message": "grid strategies are out of Phase 1",
    }


def test_seeded_nofx_strategy_is_compiled(client, token):
    rows = client.get("/api/nofx/strategies", headers=_h(token)).json()["strategies"]
    assert rows[0]["studio"]["status"] == "compiled", rows[0]["studio"]
