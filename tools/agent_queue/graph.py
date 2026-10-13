"""task-graph.json specification: the packet set the authority runs.

Minimal shape:

    {
      "tasks": [
        {"id": "A01", "deps": [], "budget_attempts": 3},
        {"id": "A02", "deps": ["A01"], "budget_attempts": 3}
      ]
    }

Cycles and self-dependencies are rejected at load time; unknown dep ids
are rejected at load time. All tasks load as BACKLOG regardless of any
status recorded in the file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BUDGET_ATTEMPTS = 3
MAX_SAME_FAILURE_REPAIRS = 3


@dataclass(frozen=True, slots=True)
class TaskSpec:
    id: str
    deps: tuple[str, ...] = ()
    budget_attempts: int = DEFAULT_BUDGET_ATTEMPTS
    resources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskGraph:
    tasks: tuple[TaskSpec, ...] = field(default_factory=tuple)

    def by_id(self) -> dict[str, TaskSpec]:
        return {t.id: t for t in self.tasks}

    @classmethod
    def load(cls, path: str | Path) -> TaskGraph:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: dict) -> TaskGraph:
        entries = raw.get("tasks")
        if not isinstance(entries, list) or not entries:
            raise ValueError("task graph must contain a non-empty 'tasks' list")
        specs: list[TaskSpec] = []
        seen: set[str] = set()
        for entry in entries:
            task_id = entry.get("id")
            if not isinstance(task_id, str) or not task_id:
                raise ValueError(f"task entry missing string id: {entry!r}")
            if task_id in seen:
                raise ValueError(f"duplicate task id: {task_id}")
            seen.add(task_id)
            deps = entry.get("deps", [])
            if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
                raise ValueError(f"task {task_id}: deps must be a list of strings")
            budget = entry.get("budget_attempts", DEFAULT_BUDGET_ATTEMPTS)
            if not isinstance(budget, int) or budget < 1:
                raise ValueError(f"task {task_id}: budget_attempts must be a positive int")
            resources = entry.get("resources", [])
            if not isinstance(resources, list) or not all(isinstance(r, str) for r in resources):
                raise ValueError(f"task {task_id}: resources must be a list of strings")
            specs.append(
                TaskSpec(
                    id=task_id,
                    deps=tuple(deps),
                    budget_attempts=budget,
                    resources=tuple(resources),
                )
            )
        known = seen
        for spec in specs:
            for dep in spec.deps:
                if dep not in known:
                    raise ValueError(f"task {spec.id} depends on unknown task {dep}")
            if spec.id in spec.deps:
                raise ValueError(f"task {spec.id} depends on itself")
        _reject_cycles(specs)
        return cls(tasks=tuple(specs))


def _reject_cycles(specs: list[TaskSpec]) -> None:
    colour: dict[str, int] = {s.id: 0 for s in specs}  # 0 white, 1 grey, 2 black

    def visit(task_id: str, by_id: dict[str, TaskSpec]) -> None:
        if colour[task_id] == 1:
            raise ValueError(f"dependency cycle involving {task_id}")
        if colour[task_id] == 2:
            return
        colour[task_id] = 1
        for dep in by_id[task_id].deps:
            visit(dep, by_id)
        colour[task_id] = 2

    by_id = {s.id: s for s in specs}
    for spec in specs:
        visit(spec.id, by_id)
