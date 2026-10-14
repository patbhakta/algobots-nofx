"""The gateway contract is law, so the laws are tested (ALG-3349, Phase 1).

ROADMAP-v3 rule 2 makes ``contracts/gateway.openapi.yaml`` the single place the
gateway's API is defined: a sprint changes it first, then regenerates the Go
client NoFX uses. These tests are what stops a later sprint from quietly
widening that surface — paper-only, idempotent order writes, one typed error
envelope, and no secret ever named in a response.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml parses the contract")

SPEC_PATH = Path(__file__).resolve().parents[2] / "contracts" / "gateway.openapi.yaml"

# P1.1's surface, as the roadmap names it.
REQUIRED_PATHS = {
    "/health": {"get"},
    "/accounts": {"get"},
    "/positions": {"get"},
    "/orders": {"get", "post"},
    "/orders/{clientOrderId}": {"get", "delete"},
    "/events": {"get"},
}

# Writes: every one of them must be replay-safe.
ORDER_WRITES = [("/orders", "post"), ("/orders/{clientOrderId}", "delete")]

SECRET_WORDS = ("secret", "password", "api_key", "apikey", "token", "credential", "private_key")


@pytest.fixture(scope="module")
def spec() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text())


def _refs(node) -> set[str]:
    """Every ``$ref`` target under ``node``, at any depth."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.add(value)
            else:
                found |= _refs(value)
    elif isinstance(node, list):
        for item in node:
            found |= _refs(item)
    return found


def _walk(node):
    """Yield every mapping in the document."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def test_spec_exists_and_is_openapi_31(spec: dict) -> None:
    assert spec["openapi"].startswith("3.1"), "3.1 — we rely on type unions and `const`"
    assert spec["info"]["title"] == "AlgoBots Gateway"


def test_spec_is_valid_openapi(spec: dict) -> None:
    """An invalid spec generates a broken Go client, so catch it here, not there."""
    validate = pytest.importorskip(
        "openapi_spec_validator", reason="openapi-spec-validator is a dev extra"
    ).validate
    validate(spec)


def test_phase1_surface_is_complete(spec: dict) -> None:
    """P1.1: /health, /accounts, /positions, /orders and /events all exist."""
    for path, methods in REQUIRED_PATHS.items():
        assert path in spec["paths"], f"{path} missing from the contract"
        defined = {m for m in spec["paths"][path] if m in {"get", "post", "put", "patch", "delete"}}
        assert methods <= defined, f"{path} is missing {sorted(methods - defined)}"


def test_every_operation_has_an_operation_id(spec: dict) -> None:
    """The generated Go client names its methods from these."""
    seen: set[str] = set()
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            op_id = op.get("operationId")
            assert op_id, f"{method.upper()} {path} has no operationId"
            assert op_id not in seen, f"operationId {op_id} is used twice"
            seen.add(op_id)


def test_paper_only_is_structural(spec: dict) -> None:
    """Roadmap rule 3: no sprint may flip an account to live.

    The mode enum having exactly one member is what makes adding LIVE a visible
    contract change with a failing test, rather than a one-word diff.
    """
    assert spec["components"]["schemas"]["Mode"]["enum"] == ["PAPER"]

    for mapping in _walk(spec):
        enum = mapping.get("enum")
        if isinstance(enum, list):
            offenders = [v for v in enum if isinstance(v, str) and v.strip().upper() == "LIVE"]
            assert not offenders, f"LIVE appears in an enum: {enum}"


def test_order_writes_require_an_idempotency_key(spec: dict) -> None:
    """P1.3's 'Done when': sending the same command twice creates one order."""
    for path, method in ORDER_WRITES:
        op = spec["paths"][path][method]
        params = list(spec["paths"][path].get("parameters", [])) + list(op.get("parameters", []))
        headers = [p for p in params if p.get("$ref", "").endswith("/IdempotencyKey")]
        assert headers, f"{method.upper()} {path} does not take an Idempotency-Key"

    key = spec["components"]["parameters"]["IdempotencyKey"]
    assert key["in"] == "header" and key["name"] == "Idempotency-Key"
    assert key["required"] is True, "an optional idempotency key is not an idempotency key"


def test_idempotency_key_is_the_client_order_id(spec: dict) -> None:
    """The key has to reach the venue, or replays only dedupe inside the gateway."""
    key_schema = "#/components/schemas/IdempotencyKeyValue"
    assert spec["components"]["parameters"]["IdempotencyKey"]["schema"]["$ref"] == key_schema
    assert spec["components"]["schemas"]["Order"]["properties"]["client_order_id"]["$ref"] == (
        key_schema
    )
    # A replay is an answer, not a second order.
    assert "200" in spec["paths"]["/orders"]["post"]["responses"]


def test_submit_order_declares_the_admission_refusals(spec: dict) -> None:
    """docs/bridge.md's admission order, surfaced as responses NoFX can switch on."""
    responses = spec["paths"]["/orders"]["post"]["responses"]
    for status in ("201", "403", "409", "422", "503"):
        assert status in responses, f"POST /orders does not document {status}"


def test_every_failure_uses_the_typed_error_envelope(spec: dict) -> None:
    """One error shape everywhere: a machine `code` plus a showable `reason`."""
    error_ref = "#/components/schemas/Error"
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for status, response in op["responses"].items():
                if not status.startswith(("4", "5")):
                    continue
                refs = _refs(response)
                assert error_ref in refs or any(
                    r.startswith("#/components/responses/") for r in refs
                ), f"{method.upper()} {path} {status} does not return the Error envelope"

    for name, response in spec["components"]["responses"].items():
        assert error_ref in _refs(response), f"shared response {name} is not an Error"

    error = spec["components"]["schemas"]["Error"]
    assert set(error["required"]) == {"code", "reason"}
    assert error["properties"]["code"]["pattern"] == "^[a-z][a-z0-9_]*$"


def test_money_and_quantities_are_strings(spec: dict) -> None:
    """Decimal-as-string: a float price is a rounding bug waiting for a fill."""
    decimal = spec["components"]["schemas"]["Decimal"]
    assert decimal["type"] == "string"

    numeric = {"qty", "filled_qty", "px", "avg_px", "limit_px", "total", "free", "locked"}
    for mapping in _walk(spec):
        for field, schema in (mapping.get("properties") or {}).items():
            if field in numeric and isinstance(schema, dict):
                assert schema.get("$ref") == "#/components/schemas/Decimal", (
                    f"{field} must be the Decimal string type, got {schema}"
                )


def test_no_schema_can_leak_a_credential(spec: dict) -> None:
    """P2.5 in advance: credentials never appear in an API response.

    Cheaper to forbid the field name now than to find it in a bundle later.
    """
    for mapping in _walk(spec):
        for field in (mapping.get("properties") or {}):
            lowered = field.lower()
            assert not any(word in lowered for word in SECRET_WORDS), (
                f"field {field!r} names a credential"
            )


def test_nautilus_pin_is_declared_in_health(spec: dict) -> None:
    """Roadmap rule 5: pinned to 2.0.0rc6; an upgrade is its own sprint."""
    health = spec["components"]["schemas"]["Health"]["properties"]
    assert health["nautilus_version"]["const"] == "2.0.0rc6"
    assert "nautilus_version" in spec["components"]["schemas"]["Health"]["required"]


def test_events_stream_is_resumable_and_deduped(spec: dict) -> None:
    """At-least-once delivery only works if the consumer gets a cursor."""
    op = spec["paths"]["/events"]["get"]
    assert "101" in op["responses"], "the WebSocket upgrade must be documented"
    assert "since" in {p["name"] for p in op["parameters"]}

    event = spec["components"]["schemas"]["Event"]
    assert "seq" in event["required"]
    assert event["properties"]["seq"]["type"] == "integer"


def test_every_ref_resolves(spec: dict) -> None:
    """A dangling $ref generates a broken client, and only at build time."""
    for ref in _refs(spec):
        assert ref.startswith("#/"), f"external $ref not allowed: {ref}"
        node = spec
        for part in ref.removeprefix("#/").split("/"):
            assert part in node, f"unresolvable $ref: {ref}"
            node = node[part]


def test_request_bodies_reject_unknown_fields(spec: dict) -> None:
    """A typo'd field in an order must be a 422, not a silently ignored key."""
    for name in ("OrderRequest", "Order", "Position", "Account", "Event", "Health", "Fill"):
        schema = spec["components"]["schemas"][name]
        assert schema.get("additionalProperties") is False, f"{name} accepts unknown fields"


# --- the gateway -> node seam (P1.3) ----------------------------------------


def test_node_command_envelope_is_typed(spec: dict) -> None:
    """P1.3: ``algobots:cmd:<node>`` has a writer and a reader, so it has a schema.

    Before P1.3 the envelope existed only in prose. A second implementation of
    an untyped envelope is how a field gets renamed on one side only.
    """
    schemas = spec["components"]["schemas"]
    envelope = schemas["NodeCommand"]
    variants = {ref for ref in _refs(envelope)}
    assert variants == {
        "#/components/schemas/SubmitOrderCommand",
        "#/components/schemas/CancelOrderCommand",
    }
    assert envelope["discriminator"]["propertyName"] == "command"

    for name in ("SubmitOrderCommand", "CancelOrderCommand"):
        assert schemas[name].get("additionalProperties") is False, (
            f"{name} accepts unknown fields — the node would ignore a typo'd command field"
        )


def test_command_carries_the_key_as_the_client_order_id(spec: dict) -> None:
    """The done-when depends on this: the key must reach the node unchanged.

    If the command typed ``client_order_id`` as a plain string, the gateway
    could hand the node something that is not the caller's key and dedupe
    would hold only in the gateway's table — which is exactly the failure
    P1.3 exists to rule out.
    """
    schemas = spec["components"]["schemas"]
    key = "#/components/schemas/IdempotencyKeyValue"
    for name in ("SubmitOrderCommand", "CancelOrderCommand"):
        assert schemas[name]["properties"]["client_order_id"]["$ref"] == key, (
            f"{name}.client_order_id is not the idempotency-key type"
        )
        assert "client_order_id" in schemas[name]["required"]

    # The cancel's own key is what makes "cancelling twice cancels once" hold.
    assert schemas["CancelOrderCommand"]["properties"]["idempotency_key"]["$ref"] == key


def test_submitted_command_is_paper_only(spec: dict) -> None:
    """Rule 3 reaches the node too: the envelope's mode is the one-member enum."""
    submit = spec["components"]["schemas"]["SubmitOrderCommand"]
    assert submit["properties"]["mode"]["$ref"] == "#/components/schemas/Mode"
    assert "mode" in submit["required"], "a command without a mode is a command to guess"
