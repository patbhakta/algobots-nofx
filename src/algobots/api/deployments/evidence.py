"""Resolve server-owned Studio evidence before creating a frozen deployment."""

import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.config import get_settings
from algobots.api.models import Strategy
from algobots.strategies.evidence import evidence_record, notebook_source
from algobots.strategies.studio import compile_studio_strategy, parse_draft


class EvidenceRequired(ValueError):
    pass


def studio_evidence(db: Session, strategy: Strategy) -> dict | None:
    """Return verified evidence for this compiled strategy, or reject it.

    Legacy non-Studio DSL strategies retain their existing deploy contract.
    A URL or hash supplied by a caller is never an evidence authorization.
    """
    drafts = db.scalars(
        select(Strategy).where(
            Strategy.tenant_id == strategy.tenant_id,
            Strategy.kind == "studio-draft",
        )
    )
    for draft in drafts:
        for artifact in draft.params.get("artifacts", []):
            if artifact.get("strategy_id") != str(strategy.id):
                continue
            # The ordinary strategies CRUD can edit compiled rows. Recompile the
            # immutable canonical draft so evidence cannot authorize changed code.
            try:
                compiled = compile_studio_strategy(
                    parse_draft(json.loads(artifact["canonical_draft"]))
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise EvidenceRequired("Invalid compiled artifact; compile again") from exc
            expected = compiled.spec or compiled.model_dump(mode="json")
            if compiled.artifact_hash != artifact["artifact_hash"] or strategy.params != expected:
                raise EvidenceRequired("Compiled artifact changed; compile and backtest again")
            settings = get_settings()
            for evidence in draft.params.get("evidence", []):
                if evidence.get("artifact_hash") != compiled.artifact_hash:
                    continue
                try:
                    result = db.get(Strategy, UUID(evidence["backtest_row_id"]))
                    if (
                        result is None
                        or result.kind != "studio-backtest"
                        or result.tenant_id != strategy.tenant_id
                        or result.params["artifact"]["artifact_hash"] != compiled.artifact_hash
                        or result.params["artifact"]["strategy_id"] != str(strategy.id)
                    ):
                        continue
                    record = evidence_record(
                        str(result.id), result.params, settings.evidence_base_url
                    )
                    if evidence != record:
                        continue
                    path = Path(settings.evidence_notebook_root) / "evidence" / f"{result.id}.py"
                    if path.read_text() != notebook_source(str(result.id), result.params):
                        continue
                except (KeyError, ValueError, OSError):
                    continue
                return record
            raise EvidenceRequired(
                "Marimo backtest evidence required for this exact compiled artifact; "
                "run Backtest first"
            )
    return None
