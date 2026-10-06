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
    Reservation,
    Signal,
    canonical_hash,
    namespace_permits,
    registry,
)
from algobots.contracts.enums import OrderType, ProductClass
from algobots.contracts.envelope import _is_secret_key

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


def _rehash(plan):
    plan["plan_hash"] = canonical_hash({k: v for k, v in plan.items() if k != "plan_hash"})
    return plan


def test_approval_covers_exact_plan_only():
    approval = ApprovalEnvelope.model_validate(load("ApprovalEnvelope"))
    plan = OrderPlan.model_validate(load("OrderPlan"))
    assert approval.violations(plan, NOW) == []

    bigger = load("OrderPlan")
    bigger["children"][0]["quantity"]["value"] = "11"
    bigger["children"][0]["max_notional"]["amount"] = "2059.75"
    reasons = approval.violations(OrderPlan.model_validate(_rehash(bigger)), NOW)
    assert "child-1: quantity exceeds approved maximum" in reasons
    assert "child-1: notional exceeds approved maximum" in reasons

    other = load("OrderPlan")
    other["children"][0]["instrument_id"] = "XNAS:TSLA"
    assert "plan hash differs from the approved hash" in approval.violations(
        OrderPlan.model_validate(_rehash(other)), NOW
    )
    assert "approval expired" in approval.violations(plan, datetime(2027, 1, 1, tzinfo=UTC))


def test_plan_hash_is_bound_to_content():
    tampered = load("OrderPlan")
    tampered["children"][0]["instrument_id"] = "XNAS:TSLA"  # approved hash kept
    with pytest.raises(ValidationError, match="plan_hash mismatch"):
        OrderPlan.model_validate(tampered)
    # Even a plan built without validation cannot pass the approval check.
    unchecked = OrderPlan.model_construct(
        **{**OrderPlan.model_validate(load("OrderPlan")).__dict__, "account_id": "acct-alpha-2"}
    )
    approval = ApprovalEnvelope.model_validate(load("ApprovalEnvelope"))
    assert "plan content does not match its plan_hash" in approval.violations(unchecked, NOW)


def test_approval_enforces_products_and_actions():
    data = load("ApprovalEnvelope")
    data["permitted_products"] = ["etf"]
    data["permitted_actions"] = ["REDUCE"]
    reasons = ApprovalEnvelope.model_validate(data).violations(
        OrderPlan.model_validate(load("OrderPlan")), NOW
    )
    assert "action PLACE_ORDER not permitted" in reasons
    assert "child-1: product equity not permitted" in reasons


def test_inventory_reservation_holds_a_quantity():
    data = load("Reservation")
    data.update(
        kind="INVENTORY",
        amount={"value": "10", "unit": "shares"},
        buffer={"value": "0", "unit": "shares"},
    )
    assert Reservation.model_validate(data).amount.unit == "shares"
    data["instrument_id"] = None
    with pytest.raises(ValidationError, match="requires instrument_id"):
        Reservation.model_validate(data)


@pytest.mark.parametrize(
    "key",
    [
        "client_secret",
        "access_token",
        "refreshToken",
        "db_password",
        "api_key",
        "privateKey",
        "Authorization",
        "auth",
        "bearer",
        "cookie",
        "Set-Cookie",
        "sessionid",
        "session_id",
        "x-api-key",
    ],
)
def test_credential_keys_are_screened(key):
    assert _is_secret_key(key)


@pytest.mark.parametrize(
    "key",
    [
        "secret_ref",
        "token_budget",
        "tokens_used",
        "keyword",
        "monkey",
        "authority_ref",
        "authority_mode",
        "session_health",
    ],
)
def test_reference_and_budget_keys_are_allowed(key):
    assert not _is_secret_key(key)


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


@pytest.mark.parametrize(
    "value",
    [
        "Bearer abcdefgh12345678",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
        "sk-ant-api03-xyz",
        "glpat-abcdefghij",
        "AIzaSyA1234567890abcdefghijklmnopqrstu",
        "sk-live-4f9a8b7c6d5e",
    ],
)
def test_credential_shaped_values_are_screened(value):
    data = load("Envelope")
    data["payload"]["reason_codes"] = [value]
    with pytest.raises(ValidationError, match="credential-shaped value"):
        Envelope.model_validate(data)


def test_grant_table_is_fingerprinted(monkeypatch):
    """R1 (ALG-3176): dict constants read by validators are part of the fingerprint."""
    from algobots.contracts import identity

    table = {k: frozenset(v) for k, v in identity.ALLOWED_GRANTS.items()}
    kind = identity.IdentityKind.EXECUTION_SERVICE
    table[kind] = table[kind] - {identity.Grant.TRADE_LIVE}
    monkeypatch.setattr(identity, "ALLOWED_GRANTS", table)
    drifted = [p for p in registry.verify_lock(registry.load_lock()) if p.startswith("Principal@")]
    assert drifted, "removing TRADE_LIVE from EXECUTION_SERVICE kept Principal@1.0's fingerprint"


def test_unknown_constant_type_fails_closed():
    class Opaque:
        pass

    with pytest.raises(TypeError, match="cannot fingerprint constant 'X'"):
        registry._constant_repr("X", Opaque())
