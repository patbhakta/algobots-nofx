"""Common command/event envelope (roadmap §1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, ClassVar

from pydantic import Field, field_validator

from . import registry
from .base import Identifier, UtcDatetime, VersionedContract
from .enums import RuntimeEnvironment

__all__ = ["Envelope"]

# Key names that must never appear anywhere in an envelope payload.
_SECRET_KEYS = frozenset(
    {"api_key", "apikey", "secret", "api_secret", "password", "passphrase", "private_key", "token"}
)


def _find_secret_keys(value: Any, path: str = "payload") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in _SECRET_KEYS:
                hits.append(child_path)
            hits.extend(_find_secret_keys(child, child_path))
    elif isinstance(value, list | tuple):
        for i, child in enumerate(value):
            hits.extend(_find_secret_keys(child, f"{path}[{i}]"))
    return hits


@registry.register
class Envelope(VersionedContract):
    """Every command/event carries this envelope; ``payload`` is a registered contract.

    Account and environment are immutable through routing (the model is frozen).
    ``payload_schema`` names the payload contract as ``Name@version``.
    """

    contract_name: ClassVar[str] = "Envelope"
    contract_version: ClassVar[str] = "1.0"

    event_id: Identifier
    tenant_id: Identifier
    account_id: Identifier | None = None
    environment: RuntimeEnvironment
    occurred_at: UtcDatetime
    received_at: UtcDatetime
    correlation_id: Identifier
    causation_id: Identifier | None = None
    producer: Identifier
    producer_revision: Identifier
    stream_id: Identifier | None = None
    sequence: Annotated[int, Field(ge=0)] | None = None
    payload_schema: Annotated[str, Field(pattern=r"^[A-Za-z]+@\d+\.\d+$")]
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def _no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        hits = _find_secret_keys(value)
        if hits:
            raise ValueError(f"secrets are never carried in envelopes: {', '.join(hits)}")
        return value

    def parse_payload(self) -> VersionedContract:
        """Validate ``payload`` against the contract version named by ``payload_schema``."""
        name, version = self.payload_schema.split("@")
        if self.payload.get("schema_version") != version:
            raise registry.UnknownContractError(
                f"payload schema_version {self.payload.get('schema_version')!r} "
                f"does not match payload_schema {self.payload_schema}"
            )
        return registry.get(name, version).model_validate(self.payload)
