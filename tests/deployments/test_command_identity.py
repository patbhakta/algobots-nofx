"""Restart identity is the admission barrier against a second interval trade."""
from uuid import UUID

import pytest

from algobots.api.deployments.command_identity import deployment_order_id
from algobots.node.commands import CLIENT_ORDER_ID

DID = UUID('438e926f-5948-44b9-903d-892bc2f57484')
HASH = 'a' * 64


def test_restart_identity_and_contract():
    first = deployment_order_id(DID, HASH, 'KXBTC15M-26OCT251745')
    assert first == deployment_order_id(str(DID), HASH, 'KXBTC15M-26OCT251745')
    assert CLIENT_ORDER_ID.fullmatch(first)
    assert len(first) <= 64


def test_isolation():
    first = deployment_order_id(DID, HASH, 'market-one')
    assert first != deployment_order_id(UUID(int=1), HASH, 'market-one')
    assert first != deployment_order_id(DID, 'b' * 64, 'market-one')
    assert first != deployment_order_id(DID, HASH, 'market-two')


@pytest.mark.parametrize('digest,event', [('', 'market'), ('A' * 64, 'market'),
                                          ('a' * 63, 'market'), (HASH, ''),
                                          (HASH, ' market'), (HASH, 'a\nb')])
def test_refuse_ambiguous_identity(digest, event):
    with pytest.raises(ValueError):
        deployment_order_id(DID, digest, event)
