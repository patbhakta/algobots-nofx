"""API proof: exact-hash, same-tenant, published evidence gates Studio deploys."""

import copy
from uuid import UUID

import pytest

from algobots.api.config import get_settings
from algobots.api.database import get_session_factory
from algobots.api.models import Strategy
from algobots.strategies.studio import translate_nofx_config
from tests.strategies.evidence_attach import attach_evidence
from tests.strategies.test_deployments_api import _make_account
from tests.strategies.test_studio import DRAFT, NOFX_MOMENTUM


@pytest.fixture()
def compiled(client, member_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("ALGOBOTS_EVIDENCE_NOTEBOOK_ROOT", str(tmp_path))
    get_settings.cache_clear()
    response = client.post("/api/studio/strategies", headers=member_headers, json=DRAFT)
    assert response.status_code == 201, response.text
    draft = response.json()
    response = client.post(f"/api/studio/strategies/{draft['id']}/compile", headers=member_headers)
    assert response.status_code == 201, response.text
    artifact = response.json()
    account = _make_account(client, member_headers)
    payload = {
        "strategy_id": artifact["strategy_id"],
        "account_id": account["id"],
        "symbol": "AAPL",
        "max_order_value": "5",
        "max_daily_loss": "20",
    }
    yield draft, artifact, payload, tmp_path
    get_settings.cache_clear()


def deploy(client, headers, compiled):
    return client.post("/api/deployments", headers=headers, json=compiled[2])


def test_refuses_without_evidence(client, member_headers, compiled):
    response = deploy(client, member_headers, compiled)
    assert response.status_code == 422
    assert "Marimo backtest evidence required" in response.json()["detail"]


def test_allows_exact_hash_and_freezes_evidence(client, member_headers, compiled):
    evidence = attach_evidence(compiled)
    response = deploy(client, member_headers, compiled)
    assert response.status_code == 201, response.text
    assert response.json()["frozen_spec"]["studio_evidence"] == evidence


@pytest.mark.parametrize("failure", ["hash", "missing", "modified", "tenant", "result"])
def test_refuses_invalid_evidence(client, member_headers, compiled, failure):
    evidence = attach_evidence(
        compiled, wrong_hash=failure == "hash", foreign_tenant=failure == "tenant"
    )
    path = compiled[3] / "evidence" / f"{evidence['backtest_row_id']}.py"
    if failure == "missing":
        path.unlink()
    if failure == "modified":
        path.write_text("# replaced")
    if failure == "result":
        with get_session_factory()() as db:
            row = db.get(Strategy, UUID(evidence["backtest_row_id"]))
            db.delete(row)
            db.commit()
    response = deploy(client, member_headers, compiled)
    assert response.status_code == 422, response.text


def test_evidence_does_not_authorize_edited_compiled_spec(client, member_headers, compiled):
    attach_evidence(compiled)
    spec = copy.deepcopy(compiled[1]["spec"])
    spec["warmup_bars"] += 1
    response = client.patch(
        f"/api/strategies/{compiled[1]['strategy_id']}",
        headers=member_headers,
        json={"params": spec},
    )
    assert response.status_code == 200, response.text
    assert deploy(client, member_headers, compiled).status_code == 422


KALSHI_DRAFT = translate_nofx_config("Kalshi BTC 15m momentum", NOFX_MOMENTUM)[0]
"""A NoFX-authored draft: compiles to a kalshi_momentum.v1 ARTIFACT_KIND row."""


@pytest.fixture()
def artifact_compiled(client, member_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("ALGOBOTS_EVIDENCE_NOTEBOOK_ROOT", str(tmp_path))
    get_settings.cache_clear()
    response = client.post(
        "/api/studio/strategies", headers=member_headers, json=KALSHI_DRAFT
    )
    assert response.status_code == 201, response.text
    draft = response.json()
    response = client.post(
        f"/api/studio/strategies/{draft['id']}/compile", headers=member_headers
    )
    assert response.status_code in (200, 201), response.text
    artifact = response.json()
    assert artifact["implementation"] == "kalshi_momentum.v1"
    account = _make_account(client, member_headers)
    payload = {
        "strategy_id": artifact["strategy_id"],
        "account_id": account["id"],
        "symbol": "KXBTC15M",
        "max_order_value": "5",
        "max_daily_loss": "20",
    }
    yield draft, artifact, payload, tmp_path
    get_settings.cache_clear()


def test_artifact_kind_refused_without_evidence(client, member_headers, artifact_compiled):
    """The evidence gate fires before the kind path: no evidence, no deploy."""
    response = client.post(
        "/api/deployments", headers=member_headers, json=artifact_compiled[2]
    )
    assert response.status_code == 422
    assert "Marimo backtest evidence required" in response.json()["detail"]


def test_artifact_kind_deploys_with_evidence_and_freezes_the_artifact(
    client, member_headers, artifact_compiled
):
    evidence = attach_evidence(artifact_compiled)
    response = client.post(
        "/api/deployments", headers=member_headers, json=artifact_compiled[2]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["artifact_hash"] == artifact_compiled[1]["artifact_hash"]
    assert body["frozen_spec"]["studio_evidence"] == evidence
    assert body["frozen_spec"]["artifact"]["implementation"] == "kalshi_momentum.v1"
