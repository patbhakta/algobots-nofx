"""Shared helper: attach published marimo backtest evidence to a Studio draft."""

import json
from uuid import UUID, uuid4

from algobots.api.config import get_settings
from algobots.api.database import get_session_factory
from algobots.api.models import Strategy
from algobots.strategies.evidence import publish_notebook


def attach_evidence(compiled, *, wrong_hash=False, foreign_tenant=False):
    """Publish an exact-hash studio-backtest row + marimo notebook on the draft."""
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
