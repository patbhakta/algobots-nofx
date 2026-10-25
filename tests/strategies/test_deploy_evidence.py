"""API proof: exact-hash, same-tenant, published evidence gates Studio deploys."""

import copy
import json
from uuid import UUID, uuid4

import pytest

from algobots.api.config import get_settings
from algobots.api.database import get_session_factory
from algobots.api.models import Strategy
from algobots.strategies.evidence import publish_notebook
from tests.strategies.test_deployments_api import _make_account
from tests.strategies.test_studio import DRAFT


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


def attach(compiled, *, wrong_hash=False, foreign_tenant=False):
    draft, artifact, _, root = compiled
    with get_session_factory()() as db:
        row = db.get(Strategy, UUID(draft["id"]))
        result = {
            "artifact": {
                "artifact_hash": "f" * 64 if wrong_hash else artifact["artifact_hash"],
                "strategy_id": artifact["strategy_id"],
            },
            "dataset": {"snapshot_id": "fixture-snapshot", "sha256": "b" * 64},
        }
        record = Strategy(
            id=uuid4(),
            tenant_id=uuid4() if foreign_tenant else row.tenant_id,
            user_id=row.user_id,
            name="backtest",
            kind="studio-backtest",
            params_json=json.dumps(result),
        )
        # Foreign tenant test uses a different *existing* tenant to respect FK checks.
        if foreign_tenant:
            from sqlalchemy import select

            from algobots.api.memberships.models import Tenant

            record.tenant_id = db.scalar(select(Tenant.id).where(Tenant.id != row.tenant_id))
        db.add(record)
        db.flush()
        evidence = publish_notebook(root, str(record.id), result, get_settings().evidence_base_url)
        params = row.params
        params["evidence"] = [evidence]
        row.params_json = json.dumps(params)
        db.commit()
        return evidence


def deploy(client, headers, compiled):
    return client.post("/api/deployments", headers=headers, json=compiled[2])


def test_refuses_without_evidence(client, member_headers, compiled):
    response = deploy(client, member_headers, compiled)
    assert response.status_code == 422
    assert "Marimo backtest evidence required" in response.json()["detail"]


def test_allows_exact_hash_and_freezes_evidence(client, member_headers, compiled):
    evidence = attach(compiled)
    response = deploy(client, member_headers, compiled)
    assert response.status_code == 201, response.text
    assert response.json()["frozen_spec"]["studio_evidence"] == evidence


@pytest.mark.parametrize("failure", ["hash", "missing", "modified", "tenant", "result"])
def test_refuses_invalid_evidence(client, member_headers, compiled, failure):
    evidence = attach(compiled, wrong_hash=failure == "hash", foreign_tenant=failure == "tenant")
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
    attach(compiled)
    spec = copy.deepcopy(compiled[1]["spec"])
    spec["warmup_bars"] += 1
    response = client.patch(
        f"/api/strategies/{compiled[1]['strategy_id']}",
        headers=member_headers,
        json={"params": spec},
    )
    assert response.status_code == 200, response.text
    assert deploy(client, member_headers, compiled).status_code == 422
