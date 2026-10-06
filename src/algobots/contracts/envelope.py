"""Common command/event envelope (roadmap §1)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, ClassVar

from pydantic import Field, field_validator, model_validator

from . import registry
from .base import Identifier, UtcDatetime, VersionedContract
from .enums import RuntimeEnvironment

__all__ = ["Envelope"]

# A payload key is treated as a credential when its last word is one of these
# (``client_secret``, ``access_token``, ``db_password``), or its last two words
# are one of the key pairs (``api_key``, ``privateKey``). ``secret_ref`` and
# ``token_budget`` end in other words and stay allowed.
_SECRET_WORDS = frozenset(
    {"secret", "password", "passwd", "passphrase", "token", "credential", "credentials"}
)
_SECRET_PAIRS = frozenset(
    {("api", "key"), ("private", "key"), ("access", "key"), ("secret", "key")}
)
_SECRET_JOINED = frozenset({"apikey", "privatekey", "accesskey", "secretkey", "apisecret"})
# Well-known credential formats, matched anywhere in a string value.
_SECRET_VALUE = re.compile(
    r"sk[-_](live|test)[-_]|\bsk-[A-Za-z0-9]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}"
    r"|\bxox[abpr]-|\bAKIA[0-9A-Z]{16}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)


def _key_words(key: str) -> list[str]:
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return [w for w in re.split(r"[^A-Za-z0-9]+", snake.lower()) if w]


def _is_secret_key(key: str) -> bool:
    words = _key_words(key)
    if not words:
        return False
    return (
        words[-1] in _SECRET_WORDS
        or words[-1] in _SECRET_JOINED
        or tuple(words[-2:]) in _SECRET_PAIRS
    )


def _find_secrets(value: Any, path: str = "payload") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _is_secret_key(str(key)):
                hits.append(child_path)
            hits.extend(_find_secrets(child, child_path))
    elif isinstance(value, list | tuple):
        for i, child in enumerate(value):
            hits.extend(_find_secrets(child, f"{path}[{i}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        hits.append(f"{path} (credential-shaped value)")
    return hits


@registry.register
class Envelope(VersionedContract):
    """Every command/event carries this envelope; ``payload`` is a registered contract,
    validated when the envelope is parsed.

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
        hits = _find_secrets(value)
        if hits:
            raise ValueError(f"secrets are never carried in envelopes: {', '.join(hits)}")
        return value

    @model_validator(mode="after")
    def _payload_parses(self) -> Envelope:
        self.parse_payload()
        return self

    def parse_payload(self) -> VersionedContract:
        """Validate ``payload`` against the contract version named by ``payload_schema``."""
        name, version = self.payload_schema.split("@")
        if self.payload.get("schema_version") != version:
            raise registry.UnknownContractError(
                f"payload schema_version {self.payload.get('schema_version')!r} "
                f"does not match payload_schema {self.payload_schema}"
            )
        return registry.get(name, version).model_validate(self.payload)
