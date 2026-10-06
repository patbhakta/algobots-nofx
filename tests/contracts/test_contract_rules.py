"""Behavioural rules carried by the A01 contracts (beyond shape validation)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from algobots.contracts import (
    ApprovalEnvelope,
    Capabilities,
    Envelope,
    MemoryScope,
    OrderPlan,
    Principal,
    Signal,
    namespace_permits,
    registry,
)
from algobots.contracts.enums import OrderType, ProductClass

VALID = Path(__file__).parent / "golden" / "valid"


def load(name):
    return json.loads((VALID / f"{name}@1.0.json").read_text())


NOW = datetime(2026, 9, 22, 15, 0, tzinfo=UTC)


def test_envelope_payload_parses_to_registered_contract():
    payload = Envelope.model_validate(load("Envelope")).parse_payload()
    assert isinstance(payload, Signal)


def test_envelope_payload_version_mismatch_fails():
    data = load("Envelope")
    data["payload_schema"] = "Signal@2.0"
    with pytest.raises(registry.UnknownContractError, match="does not match payload_schema"):
        Envelope.model_validate(data).parse_payload()


def test_envelope_normalizes_offsets_to_utc():
    data = load("Envelope")
    data["occurred_at"] = "2026-09-22T10:30:00-04:00"
    env = Envelope.model_validate(data)
    assert env.occurred_at == datetime(2026, 9, 22, 14, 30, tzinfo=UTC)
    assert env.occurred_at.tzinfo is UTC


def test_contracts_are_immutable():
    env = Envelope.model_validate(load("Envelope"))
    with pytest.raises(ValidationError):
        env.account_id = "acct-other"


def test_unknown_capability_means_disabled():
    caps = Capabilities.model_validate(load("Capabilities"))
    assert caps.is_enabled(ProductClass.EQUITY, OrderType.LIMIT)
    assert not caps.is_enabled(ProductClass.EQUITY, OrderType.STOP)
    assert caps.support_for(ProductClass.SPOT_CRYPTO, OrderType.MARKET) == "unsupported"


def test_approval_covers_exact_plan_only():
    approval = ApprovalEnvelope.model_validate(load("ApprovalEnvelope"))
    plan = OrderPlan.model_validate(load("OrderPlan"))
    assert approval.violations(plan, NOW) == []

    bigger = load("OrderPlan")
    bigger["children"][0]["quantity"]["value"] = "11"
    bigger["children"][0]["max_notional"]["amount"] = "2059.75"
    reasons = approval.violations(OrderPlan.model_validate(bigger), NOW)
    assert "child-1: quantity exceeds approved maximum" in reasons
    assert "child-1: notional exceeds approved maximum" in reasons

    rehashed = load("OrderPlan")
    rehashed["plan_hash"] = "0" * 64
    assert "plan hash differs from the approved hash" in approval.violations(
        OrderPlan.model_validate(rehashed), NOW
    )
    assert "approval expired" in approval.violations(plan, datetime(2027, 1, 1, tzinfo=UTC))


def _principal(kind, tenant, grants):
    return Principal(
        schema_version="1.0",
        principal_id=f"p-{kind.lower()}",
        kind=kind,
        tenant_id=tenant,
        grants=tuple(grants),
    )


def test_identities_are_separated_across_memory_namespaces():
    build = _principal("BUILD_AGENT", None, ["ENGINEERING_MEMORY_READ", "REPO_WRITE"])
    user = _principal("USER", "tenant-a", ["INVESTMENT_MEMORY_READ"])
    memsvc = _principal("MEMORY_SERVICE", "tenant-a", ["INVESTMENT_MEMORY_WRITE"])

    assert namespace_permits(build, "engineering/project", write=False)
    assert not namespace_permits(build, "investment/tenant-a/research", write=False)
    assert not namespace_permits(user, "engineering/project", write=False)
    assert namespace_permits(user, "investment/tenant-a/research", write=False)
    assert not namespace_permits(user, "investment/tenant-b/research", write=False)
    assert not namespace_permits(user, "investment/shared", write=True)
    assert namespace_permits(memsvc, "investment/tenant-a/accounts/acct-1", write=True)


def test_memory_scope_rejects_cross_tenant_namespace():
    user = _principal("USER", "tenant-a", ["INVESTMENT_MEMORY_READ"])
    with pytest.raises(ValidationError, match="may not read"):
        MemoryScope(principal=user, namespaces=("investment/tenant-b/research",))


def test_unknown_namespace_rejected():
    user = _principal("USER", "tenant-a", ["INVESTMENT_MEMORY_READ"])
    with pytest.raises(ValueError, match="unknown memory namespace"):
        namespace_permits(user, "investment/../tenant-b", write=False)


def test_build_agent_cannot_be_tenant_scoped():
    with pytest.raises(ValidationError, match="not tenant-scoped"):
        _principal("BUILD_AGENT", "tenant-a", ["REPO_WRITE"])
