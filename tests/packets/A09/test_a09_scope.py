"""A09 commits stay inside the A09 write scope (resolution rules from the A01 map).

The only exception is the Makefile (make-targets resource, integration owner
A01): A09 proposes its targets in tests/packets/A09/make-targets.mk and the
owner integrates them in a commit whose subject starts with `chore(make-targets)`.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "a01_map", ROOT / "tests" / "packets" / "A01" / "test_a01_repository_map.py"
)
a01 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(a01)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def test_a09_scope_is_the_declared_five_paths():
    scope = {e["path"] for e in a01.PACKETS["A09"]["write_scope"]}
    assert scope == {
        "src/algobots/dashboard/design/",
        "src/algobots/dashboard/fixtures/",
        "docs/design/",
        "tests/packets/A09/",
        "artifacts/A09/",
    }
    assert a01.PACKETS["A09"]["contract_pins"] == {}
    for path in ("src/algobots/dashboard/design/tokens.py", "artifacts/A09/acceptance.json"):
        assert a01.owner_of("algobots", path) == "A09"


def test_a09_commits_stay_inside_a09_scope():
    try:
        if _git("rev-parse", "--is-shallow-repository").strip() == "true":
            pytest.skip("shallow clone: commit parents unavailable")
        log = _git(
            "log", "--no-merges", "--format=%H %s", "--grep=ALG-3105", "--grep=ALG-3337"
        ).splitlines()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git history unavailable")
    if not log:
        pytest.skip("no A09 commits in this checkout (pre-commit run)")
    for line in log:
        sha, subject = line.split(" ", 1)
        changed = _git("diff-tree", "--no-commit-id", "--name-only", "-r", f"{sha}^", sha).split()
        if subject.startswith("chore(make-targets)"):
            assert changed == ["Makefile"], f"{sha[:7]}: make-targets commit touches {changed}"
            continue
        outside = [f for f in changed if a01.owner_of("algobots", f) != "A09"]
        assert outside == [], f"{sha[:7]} writes outside A09 scope: {outside}"


def test_proposed_make_targets_match_the_makefile():
    proposal = (ROOT / "tests" / "packets" / "A09" / "make-targets.mk").read_text()
    makefile = (ROOT / "Makefile").read_text()
    if "verify-A09:" not in makefile:
        pytest.skip("make-targets owner has not integrated the A09 proposal yet")
    body = proposal.split("# --- begin targets ---\n", 1)[1]
    assert body in makefile, "Makefile drifted from tests/packets/A09/make-targets.mk"
