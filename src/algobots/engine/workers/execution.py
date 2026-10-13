"""Execution seam for the per-account paper workers (ALG-3270, A06 slice 4).

ADR 0001 (``docs/adr/0001-nautilus-execution-spine.md``): every order and
fill goes through a Nautilus execution client. Each account's worker is built
from an ``AccountWorkerSpec`` whose ``execution`` picks the client:

- ``sandbox`` (default): the in-process simulated venue ``PAPER_<ACCT>``
  matched by Nautilus' own matching engine. No network.
- ``adapter:<name>``: a shipped Nautilus adapter's ``LiveExecutionClient``
  inside a ``TradingNode``, running the same ``DemoPaperStrategy``.
  ``adapter_node_config`` builds that node's config. Starting it would connect
  a broker account, and that is an external mutation the A06 Authority line
  has not granted. So ``PaperWorker`` refuses an adapter spec with
  ``AdapterNotAuthorized``, which names the credentials the adapter needs.

Specs come from ``ALGOBOTS_WORKER_EXECUTION`` (``laya=sandbox,jev=adapter:
interactive_brokers``). An account that isn't listed gets ``sandbox``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

SANDBOX = "sandbox"
ENV_VAR = "ALGOBOTS_WORKER_EXECUTION"
EXIT_REFUSED = 77  # EX_NOPERM: an adapter spec is a deliberate config refusal, not a lease denial


@dataclass(frozen=True)
class Adapter:
    """A shipped Nautilus US execution adapter the seam knows how to configure."""

    name: str
    venue: str
    factory: str  # importable ``LiveExecClientFactory`` path
    credentials: tuple[str, ...]  # env vars the adapter reads; never stored here
    infra: str


ADAPTERS: dict[str, Adapter] = {
    a.name: a
    for a in (
        Adapter(
            "interactive_brokers",
            "INTERACTIVE_BROKERS",
            "nautilus_trader.adapters.interactive_brokers.factories:"
            "InteractiveBrokersLiveExecClientFactory",
            ("TWS_USERNAME", "TWS_PASSWORD", "TWS_ACCOUNT"),
            "IB Gateway/TWS in paper mode on port 4002, either self-run or the adapter's "
            "dockerized gateway. The API must not be read-only to place paper orders.",
        ),
        Adapter(
            "kraken",
            "KRAKEN",
            "nautilus_trader.adapters.kraken.factories:KrakenLiveExecClientFactory",
            ("KRAKEN_FUTURES_DEMO_API_KEY", "KRAKEN_FUTURES_DEMO_API_SECRET"),
            "None. REST and WebSocket only. environment=DEMO selects the futures demo, and "
            "Kraken spot has no demo.",
        ),
    )
}


class AdapterNotAuthorized(RuntimeError):
    """An adapter spec would connect a broker account; A06 has not authorized that."""


@dataclass(frozen=True)
class AccountWorkerSpec:
    account: str
    execution: str = SANDBOX

    def __post_init__(self) -> None:
        if self.execution != SANDBOX and self.adapter is None:
            raise ValueError(
                f"{self.account}: execution must be 'sandbox' or 'adapter:<name>' with "
                f"<name> in {sorted(ADAPTERS)}, got {self.execution!r}"
            )

    @property
    def adapter(self) -> Adapter | None:
        kind, _, name = self.execution.partition(":")
        return ADAPTERS.get(name) if kind == "adapter" else None


def specs(accounts: list[str], raw: str | None = None) -> dict[str, AccountWorkerSpec]:
    """Per-account specs from ``raw`` (default: ``$ALGOBOTS_WORKER_EXECUTION``)."""
    raw = os.environ.get(ENV_VAR, "") if raw is None else raw
    chosen = dict(p.strip().split("=", 1) for p in raw.split(",") if p.strip())
    unknown = set(chosen) - set(accounts)
    if unknown:
        raise ValueError(f"{ENV_VAR}: unknown accounts {sorted(unknown)}")
    return {a: AccountWorkerSpec(a, chosen.get(a, SANDBOX).strip()) for a in accounts}


def adapter_node_config(spec: AccountWorkerSpec, trader_id: str, strategy: dict):
    """The ``TradingNodeConfig`` for an adapter spec. This builds config only and connects nothing.

    ``strategy`` is the ``DemoPaperConfig`` kwargs. The node runs the same
    ``DemoPaperStrategy`` class that the sandbox path runs.
    """
    from nautilus_trader.config import ImportableStrategyConfig, TradingNodeConfig

    a = spec.adapter
    if a is None:
        raise ValueError(f"{spec.account}: not an adapter spec ({spec.execution!r})")
    return TradingNodeConfig(
        trader_id=trader_id,
        exec_clients={a.venue: _exec_client_config(a)},
        strategies=[
            ImportableStrategyConfig(
                strategy_path="algobots.engine.workers.paper:DemoPaperStrategy",
                config_path="algobots.engine.workers.paper:DemoPaperConfig",
                config=strategy,
            )
        ],
    )


def _exec_client_config(a: Adapter):
    # Credentials stay unset: each adapter reads its own env vars when it connects.
    if a.name == "interactive_brokers":
        try:
            from nautilus_trader.adapters.interactive_brokers.config import (
                InteractiveBrokersExecClientConfig,
            )
        except ModuleNotFoundError as e:  # ibapi ships with the nautilus_trader[ib] extra
            raise RuntimeError(f"{a.name}: install nautilus_trader[ib] ({e})") from e

        return InteractiveBrokersExecClientConfig(
            ibg_port=4002, account_id=None, read_only_api=False
        )
    from nautilus_trader.adapters.kraken.config import KrakenExecClientConfig
    from nautilus_trader.core.nautilus_pyo3 import KrakenEnvironment, KrakenProductType

    return KrakenExecClientConfig(
        environment=KrakenEnvironment.DEMO, product_types=(KrakenProductType.FUTURES,)
    )


def reconcile_fills(fills: list[dict], decisions: list) -> dict:
    """Compare Nautilus fill events with the ledger's FILLED decisions, one event at a time.

    The ledger books fractional contracts (``stake / 0.50``). The venue fills
    whole contracts, rounded down. ``diff_usd`` is ledger stake minus Nautilus
    notional, so it shows that rounding exactly.
    """
    by_event = {f["event"]: f for f in fills}
    rows, missing = [], []
    for d in decisions:
        f = by_event.get(d.event)
        if f is None:
            missing.append(d.event)
            continue
        notional = Decimal(f["qty"]) * Decimal(f["px"])
        rows.append(
            {
                "event": d.event,
                "ledger_stake": str(d.stake),
                "nautilus_qty": f["qty"],
                "nautilus_px": f["px"],
                "nautilus_notional": str(notional),
                "diff_usd": str(d.stake - notional),
            }
        )
    extra = sorted(set(by_event) - {d.event for d in decisions})
    total = sum((Decimal(r["diff_usd"]) for r in rows), Decimal(0))
    return {
        "matched": len(rows),
        "missing_in_nautilus": missing,
        "extra_in_nautilus": extra,
        "total_diff_usd": str(total),
        "rows": rows,
    }
