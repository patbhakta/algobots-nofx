"""Evidence publication must preserve result identity and treat text as inert data."""

import ast
from uuid import uuid4

import pytest

from algobots.strategies.evidence import notebook_source, publish_notebook


def result():
    return {
        "artifact": {"artifact_hash": "a" * 64},
        "dataset": {"snapshot_id": "snapshot-1", "sha256": "b" * 64},
        "trades": [{"event": "'); __import__('os').system('false'); #"}],
    }


def test_publish_is_immutable_and_content_bound(tmp_path):
    identity = str(uuid4())
    payload = result()
    first = publish_notebook(tmp_path, identity, payload, "http://quantlab:8205")
    assert first == publish_notebook(tmp_path, identity, payload, "http://quantlab:8205")
    assert first["backtest_row_id"] == identity
    assert first["snapshot_id"] == "snapshot-1"
    assert first["artifact_hash"] == "a" * 64
    source = (tmp_path / "evidence" / f"{identity}.py").read_text()
    ast.parse(source)
    assert source == notebook_source(identity, payload)
    payload["dataset"]["sha256"] = "c" * 64
    with pytest.raises(ValueError, match="immutable"):
        publish_notebook(tmp_path, identity, payload, "http://quantlab:8205")
    assert (tmp_path / "evidence" / f"{identity}.py").read_text() == source


def test_invalid_result_id_cannot_escape_publication_root(tmp_path):
    with pytest.raises(ValueError):
        publish_notebook(tmp_path, "../../other", result(), "http://quantlab")
    assert not list(tmp_path.iterdir())
