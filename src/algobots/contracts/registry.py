"""Schema registry, lock and revision-safety rules (resource ``schema-registry``).

Every top-level contract registers as ``name@version``. ``schema-lock.json``
freezes the JSON-schema fingerprint of each registered version. Rules:

1. A registered version's shape is immutable: changing a model without a new
   ``contract_version`` makes its fingerprint differ from the lock, which
   :func:`verify_lock` reports as a silent revision.
2. A revision adds a new version; the old version stays registered (and
   parseable) while any queued packet pins it. :func:`check_lock_transition`
   rejects removing a pinned version or rewriting a locked fingerprint.
3. Queued packets pin ``{contract: version}`` in ``docs/repository-map.json``;
   :func:`check_pins` fails when a pin no longer resolves.

Only the schema-registry integration owner (A01, see the repository map)
updates the lock; other packets propose revisions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .base import VersionedContract

__all__ = [
    "LOCK_PATH",
    "SchemaRevisionError",
    "UnknownContractError",
    "check_lock_transition",
    "check_pins",
    "current_lock",
    "fingerprint",
    "get",
    "load_lock",
    "parse",
    "register",
    "registered",
    "verify_lock",
    "write_lock",
]

LOCK_PATH = Path(__file__).with_name("schema-lock.json")

_REGISTRY: dict[tuple[str, str], type[VersionedContract]] = {}


class UnknownContractError(LookupError):
    """No registered contract matches the requested name/version."""


class SchemaRevisionError(ValueError):
    """A schema change would silently invalidate a lock entry or a queued pin."""


def register[T: type[VersionedContract]](cls: T) -> T:
    key = (cls.contract_name, cls.contract_version)
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise SchemaRevisionError(f"{key[0]}@{key[1]} is already registered")
    _REGISTRY[key] = cls
    return cls


def registered() -> dict[tuple[str, str], type[VersionedContract]]:
    return dict(sorted(_REGISTRY.items()))


def get(name: str, version: str) -> type[VersionedContract]:
    try:
        return _REGISTRY[(name, version)]
    except KeyError:
        known = sorted(v for (n, v) in _REGISTRY if n == name)
        raise UnknownContractError(
            f"{name}@{version} is not registered"
            + (f"; supported versions: {', '.join(known)}" if known else "; unknown contract")
        ) from None


def parse(name: str, data: Mapping[str, Any]) -> VersionedContract:
    """Validate ``data`` against the registered version it declares."""
    version = data.get("schema_version")
    if not isinstance(version, str):
        raise UnknownContractError(f"{name}: payload has no string schema_version")
    return get(name, version).model_validate(data)


def fingerprint(cls: type[VersionedContract]) -> str:
    schema = cls.model_json_schema(mode="validation")
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def current_lock() -> dict[str, dict[str, str]]:
    lock: dict[str, dict[str, str]] = {}
    for (name, version), cls in registered().items():
        lock.setdefault(name, {})[version] = fingerprint(cls)
    return lock


def load_lock(path: Path = LOCK_PATH) -> dict[str, dict[str, str]]:
    return json.loads(path.read_text())["contracts"]


def verify_lock(lock: Mapping[str, Mapping[str, str]]) -> list[str]:
    """Return human-readable drift between the registry and ``lock`` (empty = in sync)."""
    problems: list[str] = []
    live = current_lock()
    for name, versions in live.items():
        for version, fp in versions.items():
            locked = lock.get(name, {}).get(version)
            if locked is None:
                problems.append(f"{name}@{version} is registered but not in the lock")
            elif locked != fp:
                problems.append(
                    f"{name}@{version} changed shape without a version bump "
                    f"(lock {locked[:12]}, live {fp[:12]})"
                )
    for name, versions in lock.items():
        for version in versions:
            if version not in live.get(name, {}):
                problems.append(f"{name}@{version} is locked but no longer registered")
    return problems


def check_pins(
    pins: Mapping[str, Mapping[str, str]], lock: Mapping[str, Mapping[str, str]]
) -> None:
    """Fail when any packet's pinned ``{contract: version}`` is absent from ``lock``."""
    broken = [
        f"{packet} pins {name}@{version}"
        for packet, packet_pins in sorted(pins.items())
        for name, version in sorted(packet_pins.items())
        if version not in lock.get(name, {})
    ]
    if broken:
        raise SchemaRevisionError("unresolvable contract pins: " + "; ".join(broken))


def check_lock_transition(
    old: Mapping[str, Mapping[str, str]],
    new: Mapping[str, Mapping[str, str]],
    queued_pins: Mapping[str, Mapping[str, str]],
) -> None:
    """Reject a lock revision that rewrites a locked version or strands a queued pin.

    Adding versions is always allowed. Removing a version is allowed only when
    no queued packet pins it.
    """
    errors: list[str] = []
    for name, versions in old.items():
        for version, fp in versions.items():
            if version in new.get(name, {}) and new[name][version] != fp:
                errors.append(f"{name}@{version} fingerprint rewritten in place")
    pinned_by: dict[tuple[str, str], list[str]] = {}
    for packet, packet_pins in queued_pins.items():
        for name, version in packet_pins.items():
            pinned_by.setdefault((name, version), []).append(packet)
    for (name, version), packets in sorted(pinned_by.items()):
        if version in old.get(name, {}) and version not in new.get(name, {}):
            errors.append(
                f"{name}@{version} removed while queued packets pin it: "
                + ", ".join(sorted(packets))
            )
    if errors:
        raise SchemaRevisionError("; ".join(errors))


def write_lock(path: Path = LOCK_PATH) -> None:
    """Regenerate the lock from the registry. Integration owner only (see module docstring)."""
    body = {
        "resource": "schema-registry",
        "integration_owner": "A01",
        "rule": "a locked name@version is immutable; revise by registering a new version",
        "contracts": current_lock(),
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
