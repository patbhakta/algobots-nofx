"""The A14 branch only touches paths A14 may write (A03 guard convention).

Compares `git diff --name-only <merge-base with origin/main>..HEAD` with the
`packets.A14.write_scope` entries in `docs/repository-map.json` (read-only
reference). Skips when git or origin/main isn't available, and passes
trivially once the branch is merged (empty diff).

A14's frozen write scope describes what an *A14 branch* may touch, so the
guard only runs on one. On any other branch — a ROADMAP-v3 sprint branch, say
— every path it adds is "outside A14", which says nothing about A14
discipline (ALG-3373).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
REPO = "algobots"
PACKET = "A14"

# Mechanical exception (reported to the TL on the issue per packet law): the
# frozen scope lists `src/algobots/knowledge/ingest/`, and creating that new
# subpackage requires the one-line parent package marker next to it. Nothing
# else under src/algobots/knowledge/ is allowed by this guard.
#
# (The `pipeline/flows/algobots-ingest.yaml` exception added in ALG-3320 was
# dropped at TL integration: docs/repository-map.json now attributes that
# path to repo "algobots", so it is covered by the write_scope entries.)
MECHANICAL_PACKAGE_MARKERS = frozenset(
    {
        "src/algobots/knowledge/__init__.py",
    }
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _changed_files() -> list[str]:
    try:
        base = _git("merge-base", "origin/main", "HEAD")
        return [p for p in _git("diff", "--name-only", f"{base}..HEAD").splitlines() if p]
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git or origin/main unavailable")


def _branch_under_test() -> str:
    """The branch the diff belongs to: the PR source in CI, else the checkout."""
    for var in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        ref = os.environ.get(var, "").strip()
        if ref:
            return ref
    try:
        return _git("rev-parse", "--abbrev-ref", "HEAD")
    except (OSError, subprocess.CalledProcessError):
        return ""


def _is_packet_branch(branch: str) -> bool:
    """`feat/alg-3110-a14-1-ingest-core` is A14's; `alg-3373-p15-e2e-gate` is not."""
    return PACKET.lower() in re.split(r"[^a-z0-9]+", branch.lower())


def _allowed_paths() -> set[str]:
    repo_map = json.loads((ROOT / "docs" / "repository-map.json").read_text())
    allowed = {
        entry["path"]
        for entry in repo_map["packets"]["A14"]["write_scope"]
        if entry["repo"] == REPO
    }
    assert allowed, "A14 write_scope missing from repository-map.json"
    return allowed


def _is_within(path: str, allowed_root: str) -> bool:
    root = allowed_root.rstrip("/")
    return path == root or path.startswith(root + "/")


def test_branch_stays_inside_a14_write_scope():
    branch = _branch_under_test()
    if not _is_packet_branch(branch):
        pytest.skip(f"{branch!r} is not an {PACKET} branch; its write scope does not apply")
    changed = _changed_files()
    if not changed:
        pytest.skip("empty diff (merged or fresh branch)")
    allowed = _allowed_paths()
    violations = [
        p
        for p in changed
        if p not in MECHANICAL_PACKAGE_MARKERS
        and not any(_is_within(p, root) for root in allowed)
    ]
    assert violations == [], (
        f"files outside the frozen A14 write scope: {violations}; "
        "allowed roots: " + ", ".join(sorted(allowed))
    )


def test_packet_branch_detection():
    assert _is_packet_branch("feat/alg-3110-a14-1-ingest-core")
    assert _is_packet_branch("merge/alg-3110-A14")
    assert not _is_packet_branch("alg-3373-p15-e2e-gate")
    assert not _is_packet_branch("feat/alg-3099-a03-tenant-auth")
    assert not _is_packet_branch("main")
    assert not _is_packet_branch("")
