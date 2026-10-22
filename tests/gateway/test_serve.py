"""The deployed gateway's wiring (ALG-3404): env -> registry, sessions, gate, streams."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from algobots.gateway.admission import OrderIntent
from algobots.gateway.auth import NoSessions
from algobots.gateway.serve import (
    KILL_SWITCH,
    QTY_LIMIT,
    ensure_command_streams,
    gate_from,
    registry_from,
    sessions_from,
)
from algobots.node.command_stream import GROUP

NODE = {
    "node": "nautilus-paper-1",
    "account_id": "paper-1",
    "display_name": "Paper 1",
    "venue": "SIM",
    "nautilus_account_id": "SIM-001",
}


def _intent(qty: str) -> OrderIntent:
    return OrderIntent(
        client_order_id="k-00000001",
        account_id="paper-1",
        node="nautilus-paper-1",
        symbol="EUR/USD.SIM",
        side="buy",
        qty=Decimal(qty),
        order_type="market",
    )


class FakeRedis:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.groups: set[tuple[str, str]] = {(k, GROUP) for k in existing or set()}

    def xgroup_create(self, key: str, group: str, id: str, mkstream: bool) -> None:  # noqa: A002
        assert mkstream and id == "0"
        if (key, group) in self.groups:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        self.groups.add((key, group))


def test_registry_reads_nodes_and_refuses_live() -> None:
    reg = registry_from(json.dumps([NODE]))
    assert [n.node for n in reg.accounts()] == ["nautilus-paper-1"]
    with pytest.raises(ValueError, match="paper only"):
        registry_from(json.dumps([{**NODE, "mode": "LIVE"}]))
    assert registry_from(None).accounts() == []


def test_sessions_fail_closed_when_unset() -> None:
    assert isinstance(sessions_from(None), NoSessions)
    s = sessions_from(json.dumps({"tok": {"principal": "pat", "accounts": ["paper-1"]}}))
    assert s.caller("tok").accounts == ("paper-1",)
    assert s.caller("other") is None


def test_gate_kill_switch_and_qty_limit() -> None:
    assert gate_from({}).pre_trade(_intent("1000")).allowed
    assert gate_from({"ALGOBOTS_GATEWAY_KILL": "1"}).pre_trade(_intent("1")).code == KILL_SWITCH
    capped = gate_from({"ALGOBOTS_GATEWAY_MAX_QTY": "10"})
    assert capped.pre_trade(_intent("10")).allowed
    assert capped.pre_trade(_intent("10.5")).code == QTY_LIMIT


def test_command_streams_created_idempotently() -> None:
    reg = registry_from(json.dumps([NODE]))
    client = FakeRedis(existing={"algobots:cmd:nautilus-paper-1"})
    assert ensure_command_streams(client, reg) == ["algobots:cmd:nautilus-paper-1"]
    fresh = FakeRedis()
    ensure_command_streams(fresh, reg)
    assert fresh.groups == {("algobots:cmd:nautilus-paper-1", GROUP)}
