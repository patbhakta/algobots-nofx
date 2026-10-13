"""TaskGraph load-time checks (A02): the specification is strict."""

from __future__ import annotations

import json

import pytest
from tools.agent_queue.graph import DEFAULT_BUDGET_ATTEMPTS, TaskGraph


def graph(tmp_path, payload: dict) -> str:
    path = tmp_path / "task-graph.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_minimal_graph_loads(tmp_path):
    g = TaskGraph.load(graph(tmp_path, {"tasks": [{"id": "A01"}]}))
    assert [s.id for s in g.tasks] == ["A01"]
    spec = g.by_id()["A01"]
    assert spec.deps == () and spec.budget_attempts == DEFAULT_BUDGET_ATTEMPTS
    assert spec.resources == ()


def test_statuses_in_the_file_are_ignored_all_load_backlog(tmp_path):
    payload = {"tasks": [{"id": "A01", "status": "DONE"}]}
    g = TaskGraph.load(graph(tmp_path, payload))
    assert g.by_id()["A01"].id == "A01"  # status key is not part of the spec


def test_deps_budget_and_resources_round_trip(tmp_path):
    payload = {
        "tasks": [
            {"id": "A00", "deps": [], "budget_attempts": 5, "resources": ["task-authority"]},
            {"id": "A02", "deps": ["A00"], "budget_attempts": 3},
        ]
    }
    g = TaskGraph.load(graph(tmp_path, payload))
    assert g.by_id()["A00"].resources == ("task-authority",)
    assert g.by_id()["A02"].deps == ("A00",)


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"tasks": []}, "non-empty"),
        ({}, "non-empty"),
        ({"tasks": [{"id": "A"}, {"id": "A"}]}, "duplicate task id"),
        ({"tasks": [{"id": "A", "deps": ["NOPE"]}]}, "unknown task"),
        ({"tasks": [{"id": "A", "deps": ["A"]}]}, "depends on itself"),
        (
            {"tasks": [{"id": "A", "deps": ["B"]}, {"id": "B", "deps": ["A"]}]},
            "cycle",
        ),
        ({"tasks": [{"id": "A", "budget_attempts": 0}]}, "positive int"),
        ({"tasks": [{"id": "A", "budget_attempts": "3"}]}, "positive int"),
        ({"tasks": [{"id": "A", "resources": [7]}]}, "list of strings"),
        ({"tasks": [{"deps": []}]}, "missing string id"),
    ],
)
def test_invalid_graphs_are_rejected_at_load(tmp_path, payload, message):
    with pytest.raises(ValueError, match=message):
        TaskGraph.from_mapping(payload)


def test_longer_cycle_is_rejected(tmp_path):
    payload = {
        "tasks": [
            {"id": "A", "deps": ["C"]},
            {"id": "B", "deps": ["A"]},
            {"id": "C", "deps": ["B"]},
        ]
    }
    with pytest.raises(ValueError, match="cycle"):
        TaskGraph.from_mapping(payload)
