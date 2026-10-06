"""Contract primitives shared by every A01 schema.

- :class:`ContractModel` — immutable, unknown fields rejected.
- :class:`VersionedContract` — a top-level contract carrying an explicit
  ``schema_version``; a payload with any other version fails clearly instead
  of being coerced.
- :data:`DecimalStr` — amounts/quantities cross the wire as decimal strings.
  Floats and ints are rejected so binary rounding can never enter a ledger.
- :class:`Money` / :class:`Quantity` — a decimal always travels with an
  explicit currency or unit.
- :data:`UtcDatetime` — RFC3339 with an explicit offset, normalized to UTC;
  naive timestamps are rejected.
- :data:`Probability` / :data:`BoundedScore` — finite bounded JSON numbers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, ClassVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
)

__all__ = [
    "BoundedScore",
    "ContractModel",
    "DecimalStr",
    "Identifier",
    "Money",
    "Probability",
    "Quantity",
    "Sha256Hex",
    "UtcDatetime",
    "VersionedContract",
]


def _parse_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or isinstance(value, int | float):
        raise ValueError(f"decimal amounts must be strings, got {type(value).__name__} {value!r}")
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"not a decimal string: {value!r}") from exc
    else:
        raise ValueError(f"decimal amounts must be strings, got {type(value).__name__}")
    if not parsed.is_finite():
        raise ValueError(f"decimal must be finite, got {value!r}")
    return parsed


DecimalStr = Annotated[
    Decimal,
    BeforeValidator(_parse_decimal),
    PlainSerializer(lambda d: format(d, "f"), return_type=str),
]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must carry an explicit UTC offset (RFC3339)")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]

Probability = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
BoundedScore = Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:/#@-]+$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_CURRENCY = r"^[A-Z0-9]{3,10}$"


class ContractModel(BaseModel):
    """Base for all contract shapes: frozen, unknown fields rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


class VersionedContract(ContractModel):
    """A registered top-level contract. Subclasses set ``contract_name``/``contract_version``."""

    contract_name: ClassVar[str]
    contract_version: ClassVar[str]

    schema_version: str

    @field_validator("schema_version")
    @classmethod
    def _exact_version(cls, value: str) -> str:
        if value != cls.contract_version:
            raise ValueError(
                f"{cls.contract_name}: schema_version {value!r} is not "
                f"{cls.contract_version!r}; parse through the registry to select a version"
            )
        return value


class Money(ContractModel):
    """A decimal amount in an explicit currency (ISO 4217 or a venue asset code)."""

    amount: DecimalStr
    currency: Annotated[str, Field(pattern=_CURRENCY)]


class Quantity(ContractModel):
    """A decimal quantity in an explicit unit (``shares``, ``BTC``, ``contracts``...)."""

    value: DecimalStr
    unit: Annotated[str, Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_]+$")]
