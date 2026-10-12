"""A01 acceptance case 2: every packet resolves to real/proposed paths and each
shared resource has one integration owner. Also pins the harness freeze, the
recorded scope revisions, map exhaustiveness and A01's own write scope."""

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MAP = json.loads((REPO_ROOT / "docs" / "repository-map.json").read_text())
PACKETS = MAP["packets"]
RESOURCES = MAP["shared_resources"]
EXPECTED_IDS = {f"A{n:02d}" for n in range(38)}


def _covers(prefix: str, path: str) -> bool:
    return prefix == "" or path == prefix or (prefix.endswith("/") and path.startswith(prefix))


def owner_of(repo: str, path: str) -> str | None:
    """Resolve a tracked file to its owner using the map's resolution rules."""
    for frozen in MAP["frozen_paths"]:
        if frozen["repo"] == repo and any(_covers(p, path) for p in frozen["paths"]):
            return f"frozen:{frozen['source_issue']}"
    best: tuple[int, str] | None = None
    for pid, packet in PACKETS.items():
        for entry in packet["write_scope"]:
            if entry["repo"] == repo and _covers(entry["path"], path):
                if best is None or len(entry["path"]) > best[0]:
                    best = (len(entry["path"]), pid)
    if best:
        return best[1]
    for name, res in RESOURCES.items():
        if any(p["repo"] == repo and _covers(p["path"], path) for p in res["paths"]):
            return f"resource:{name}"
    if any(e["repo"] == repo and e["path"] == path for e in MAP["integrator_owned"]):
        return "integrator"
    return None


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def test_all_38_packets_present_with_known_dependencies():
    assert set(PACKETS) == EXPECTED_IDS
    for pid, packet in PACKETS.items():
        assert set(packet["dependencies"]) <= EXPECTED_IDS, pid


def test_dependency_graph_is_acyclic():
    state: dict[str, int] = {}

    def visit(pid: str) -> None:
        assert state.get(pid) != 1, f"dependency cycle through {pid}"
        if state.get(pid) == 2:
            return
        state[pid] = 1
        for dep in PACKETS[pid]["dependencies"]:
            visit(dep)
        state[pid] = 2

    for pid in PACKETS:
        visit(pid)


@pytest.mark.parametrize("pid", sorted(EXPECTED_IDS))
def test_packet_resolves_to_real_or_proposed_paths(pid):
    packet = PACKETS[pid]
    assert packet["write_scope"], f"{pid} has no write scope"
    for entry in packet["write_scope"]:
        assert entry["repo"] in MAP["repositories"], entry
        assert entry["repo"] in packet["repositories"], entry
        assert entry["status"] in {"real", "proposed"}, entry
        assert not entry["path"].startswith("/") and ".." not in entry["path"], entry
        if entry["repo"] == "algobots" and entry["status"] == "real":
            assert (REPO_ROOT / entry["path"]).exists(), f"{pid}: {entry['path']} marked real"
    assert any(e["path"] == f"tests/packets/{pid}/" for e in packet["write_scope"])
    assert any(e["path"] == f"artifacts/{pid}/" for e in packet["write_scope"])


def test_no_two_packets_declare_the_same_path():
    seen: dict[tuple[str, str], str] = {}
    for pid, packet in PACKETS.items():
        for entry in packet["write_scope"]:
            key = (entry["repo"], entry["path"])
            assert key not in seen, f"{key} declared by {seen.get(key)} and {pid}"
            seen[key] = pid


def test_each_shared_resource_has_exactly_one_known_integration_owner():
    used = {r for p in PACKETS.values() for r in p["shared_resources"]}
    assert used <= set(RESOURCES), used - set(RESOURCES)
    for name, res in RESOURCES.items():
        owner = res["integration_owner"]
        assert isinstance(owner, str) and owner in PACKETS, name
        assert name in PACKETS[owner]["shared_resources"], f"{owner} does not hold {name}"


def test_shared_resource_paths_overlap_only_declared_carve_outs():
    """A non-owner write scope inside a resource path must be a recorded carve-out."""
    for name, res in RESOURCES.items():
        carved = {(c["repo"], c["path"], c["packet"]) for c in res.get("carve_outs", [])}
        for pid, packet in PACKETS.items():
            if pid == res["integration_owner"]:
                continue
            for entry in packet["write_scope"]:
                for rpath in res["paths"]:
                    if rpath["repo"] != entry["repo"]:
                        continue
                    overlap = _covers(rpath["path"], entry["path"]) or _covers(
                        entry["path"], rpath["path"]
                    )
                    if overlap:
                        key = (entry["repo"], entry["path"], pid)
                        assert key in carved, f"{pid} {entry['path']} overlaps resource {name}"
        for repo, path, pid in carved:
            assert any(e["repo"] == repo and e["path"] == path for e in PACKETS[pid]["write_scope"])


def test_harness_is_frozen_and_unwritable():
    (harness,) = MAP["frozen_paths"]
    assert harness["paths"] == ["src/algobots/evals/harness/", "tests/evals/harness/"]
    assert harness["source_issue"] == "ALG-3086"
    assert harness["head_commit"] == "b340c99"
    assert harness["writers"] == []
    assert set(harness["readers"]) >= {"A18", "A28"}
    for pid, packet in PACKETS.items():
        for entry in packet["write_scope"]:
            for frozen in harness["paths"]:
                overlap = _covers(entry["path"], frozen) or _covers(frozen, entry["path"])
                assert not overlap, f"{pid} write scope {entry['path']} overlaps {frozen}"


def test_scope_revisions_match_packet_revisions():
    for pid, packet in PACKETS.items():
        expected = 1 + sum(1 for r in MAP["scope_revisions"] if r["packet"] == pid)
        assert packet["revision"] == expected, pid
    for rev in MAP["scope_revisions"]:
        paths = {e["path"] for e in PACKETS[rev["packet"]]["write_scope"]}
        assert not set(rev["removed"]) & paths, rev
        assert set(rev["added"]) <= paths, rev


def test_every_tracked_file_has_an_owner():
    try:
        files = _git("ls-files").split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git unavailable")
    orphans = [f for f in files if owner_of("algobots", f) is None]
    assert orphans == []


def test_a01_commits_stay_inside_a01_scope():
    def a01_covers(path: str) -> bool:
        # Longest-prefix ownership can shadow A01 paths when a later packet's
        # scope revision carves a finer-grained co-owned subtree out of them
        # (e.g. A04 rev3 took tests/contracts/golden/valid/). A01 commits that
        # stay inside A01's own declared scope are in-scope regardless of the
        # current longest-prefix winner.
        return any(
            entry["repo"] == "algobots" and _covers(entry["path"], path)
            for entry in PACKETS["A01"]["write_scope"]
        )

    try:
        if _git("rev-parse", "--is-shallow-repository").strip() == "true":
            pytest.skip("shallow clone: commit parents unavailable")
        shas = _git("log", "--no-merges", "--format=%H", "--grep=ALG-3097").split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git history unavailable")
    if not shas:
        pytest.skip("no A01 commits in this checkout (pre-commit run)")
    for sha in shas:
        changed = _git("diff-tree", "--no-commit-id", "--name-only", "-r", f"{sha}^", sha).split()
        outside = [f for f in changed if owner_of("algobots", f) != "A01" and not a01_covers(f)]
        assert outside == [], f"{sha[:7]} writes outside A01 scope: {outside}"
