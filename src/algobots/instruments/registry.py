"""Canonical instrument registry (A05, roadmap §2 checklist item 1).

The registry is code + fixtures (no DB): entries are :class:`Instrument`
contract payloads in a bundled JSON spec, versioned by ``metadata_version``.
Identity is the frozen triple ``{venue}:{product}:{symbol}`` — BTC/USD spot at
two venues and a BTC perpetual are three distinct executable IDs.

Known seams (not re-homed here): A06's ``engine/workers/paper.py`` builds
ad-hoc Nautilus instruments for demo sleeves (Kalshi binary options), and
``engine/sleeve.py`` mints Kalshi ``Symbol(f"{event}-{outcome}")`` identities.
Those are a different asset class excluded from A05; when equities/spot-crypto
workers need identities they must resolve through this registry.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from algobots.contracts.instrument import Instrument

__all__ = [
    "InstrumentRegistry",
    "InstrumentRegistryError",
    "UnknownInstrumentError",
    "default_registry",
    "spec_path",
]


class InstrumentRegistryError(ValueError):
    """The spec file is internally inconsistent."""


class UnknownInstrumentError(KeyError):
    """No instrument matches the requested executable ID or triple."""


class InstrumentRegistry:
    """Immutable view over one instrument spec revision."""

    def __init__(self, instruments: tuple[Instrument, ...]) -> None:
        by_id: dict[str, Instrument] = {}
        by_triple: dict[tuple[str, str, str], Instrument] = {}
        for inst in instruments:
            if inst.instrument_id in by_id:
                raise InstrumentRegistryError(f"duplicate instrument_id {inst.instrument_id}")
            triple = (inst.venue, str(inst.product), inst.symbol)
            if triple in by_triple:
                raise InstrumentRegistryError(
                    f"duplicate (venue, product, symbol) {triple} — identities must be distinct"
                )
            by_id[inst.instrument_id] = inst
            by_triple[triple] = inst
        self._by_id = by_id
        self._by_triple = by_triple

    def get(self, instrument_id: str) -> Instrument:
        try:
            return self._by_id[instrument_id]
        except KeyError:
            raise UnknownInstrumentError(
                f"{instrument_id} is not a registered executable ID "
                f"(known: {', '.join(sorted(self._by_id))})"
            ) from None

    def resolve(self, venue: str, product: str, symbol: str) -> Instrument:
        try:
            return self._by_triple[(venue, product, symbol)]
        except KeyError:
            raise UnknownInstrumentError(
                f"no instrument for ({venue}, {product}, {symbol})"
            ) from None

    def list(self) -> tuple[Instrument, ...]:
        return tuple(self._by_id[k] for k in sorted(self._by_id))

    def __contains__(self, instrument_id: str) -> bool:
        return instrument_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)

    @classmethod
    def load(cls, path: Path) -> tuple[InstrumentRegistry, dict[str, tuple[str, ...]]]:
        """Build from a spec file; returns the registry and the research directory."""
        doc = json.loads(path.read_text())
        instruments = tuple(
            Instrument.model_validate(entry) for entry in doc.get("instruments", [])
        )
        research_raw = doc.get("research", {})
        research: dict[str, tuple[str, ...]] = {}
        for key, ids in research_raw.items():
            resolved = tuple(str(i) for i in ids)
            unknown = [i for i in resolved if i not in {x.instrument_id for x in instruments}]
            if unknown:
                raise InstrumentRegistryError(
                    f"research key {key} references unknown instruments {unknown}"
                )
            research[str(key)] = resolved
        return cls(instruments), research


def spec_path() -> Path:
    return Path(__file__).with_name("instruments.json")


@lru_cache(maxsize=1)
def default_registry() -> InstrumentRegistry:
    """The bundled canonical registry (deterministic; no I/O beyond the spec file)."""
    registry, _ = InstrumentRegistry.load(spec_path())
    return registry
