"""Read-only source snapshotting (A14-1): snapshot BEFORE any parsing.

The walker never follows symlinks, never writes inside the source root, and
classifies every symlink it meets: an escape is rejected with a security
finding, an inside-root symlink is skipped with a visible finding (we do not
double-count identities through links). Nothing outside the registered root
is ever opened or hashed.

A snapshot is identified by the sha256 of its sorted manifest (path + content
hash + size), so identical source content yields the same snapshot id and the
existing snapshot is reused — no duplicate copies, no downstream work. The
manifest.json is written LAST: a snapshot without a manifest is incomplete
and rebuilt on the next run.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from algobots.knowledge.ingest.security import resolve_within_root, symlink_escape_target

# Vault-internal directories (all dot-prefixed in practice; the walker skips
# every dot-entry, this set documents the known ones).
SKIP_DIRS = frozenset({".git", ".obsidian", ".trash", ".stfolder"})

MARKDOWN_SUFFIX = ".md"

# Asset suffix -> capability required to extract. Anything NOT listed here and
# not .md is queued with capability "unknown" (visible, unsupported — this
# table is an explicit, non-universal claim).
ASSET_CAPABILITIES: dict[str, str] = {
    ".pdf": "pdf-text",
    ".png": "ocr",
    ".jpg": "ocr",
    ".jpeg": "ocr",
    ".gif": "ocr",
    ".webp": "ocr",
    ".tif": "ocr",
    ".tiff": "ocr",
    ".csv": "table-parse",
    ".tsv": "table-parse",
    ".xlsx": "table-parse",
}


def capability_for(suffix: str) -> tuple[bool, str]:
    """(is_markdown, capability) for a file suffix."""
    s = suffix.lower()
    if s == MARKDOWN_SUFFIX:
        return True, "markdown"
    return False, ASSET_CAPABILITIES.get(s, "unknown")


@dataclass(frozen=True)
class SnapshotFile:
    path: str  # POSIX relative path inside the source root
    content_hash: str
    size_bytes: int
    is_markdown: bool
    capability: str  # "markdown" | capability name | "unknown"


@dataclass(frozen=True)
class SecurityFinding:
    path: str
    reason: str  # symlink_escape | symlink_skipped
    message: str
    target: str | None = None  # resolved outside target (escape case only)


@dataclass(frozen=True)
class SnapshotResult:
    source_id: str
    snapshot_id: str
    files: tuple[SnapshotFile, ...]
    findings: tuple[SecurityFinding, ...]
    created: bool  # True when a new snapshot tree was written

    def markdown_files(self) -> tuple[SnapshotFile, ...]:
        return tuple(f for f in self.files if f.is_markdown)

    def asset_files(self) -> tuple[SnapshotFile, ...]:
        return tuple(f for f in self.files if not f.is_markdown)


def _hash_file(p: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with p.open("rb") as f:
        while True:
            block = f.read(1 << 20)
            if not block:
                break
            size += len(block)
            h.update(block)
    return h.hexdigest(), size


def _walk(root: Path) -> tuple[list[Path], list[SecurityFinding]]:
    """Depth-first, sorted, symlink-safe listing of files under root."""
    files: list[Path] = []
    findings: list[SecurityFinding] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir(), key=lambda e: e.name):
            if entry.name.startswith("."):
                continue  # dot-entries are vault/plumbing internals (see SKIP_DIRS)
            if entry.is_symlink():
                target = symlink_escape_target(root, entry)
                rel = entry.relative_to(root).as_posix()
                if target is not None:
                    findings.append(
                        SecurityFinding(
                            path=rel,
                            reason="symlink_escape",
                            message=(
                                f"symlink resolves outside the source root; "
                                f"rejected without reading: {rel} -> {target}"
                            ),
                            target=str(target),
                        )
                    )
                else:
                    findings.append(
                        SecurityFinding(
                            path=rel,
                            reason="symlink_skipped",
                            message=(
                                f"inside-root symlink skipped (no identity "
                                f"doubling through links): {rel}"
                            ),
                        )
                    )
                continue
            if entry.is_dir():
                stack.append(entry)
            else:
                files.append(entry)
    return files, findings


def snapshot_source(store, source) -> SnapshotResult:
    """Hash every safe file under the source root, then copy them once into
    an immutable, content-keyed snapshot tree. Idempotent: unchanged content
    re-detects the existing snapshot and writes nothing."""
    root = Path(source.root).resolve()
    raw_files, findings = _walk(root)

    manifest: list[SnapshotFile] = []
    for f in raw_files:
        rel = f.relative_to(root).as_posix()
        safe = resolve_within_root(root, rel)  # re-verify confinement per file
        content_hash, size = _hash_file(safe)
        is_md, capability = capability_for(f.suffix)
        manifest.append(
            SnapshotFile(
                path=rel,
                content_hash=content_hash,
                size_bytes=size,
                is_markdown=is_md,
                capability=capability,
            )
        )
    manifest.sort(key=lambda m: m.path)

    snapshot_id = _manifest_hash(manifest)
    snap_dir = store.snapshot_dir(source.source_id, snapshot_id)
    if store.has_snapshot(source.source_id, snapshot_id):
        return SnapshotResult(source.source_id, snapshot_id, tuple(manifest),
                              tuple(findings), created=False)

    if snap_dir.exists():
        shutil.rmtree(snap_dir)  # incomplete snapshot without manifest: rebuild
    snap_dir.mkdir(parents=True, exist_ok=True)  # empty vaults snapshot too
    for m in manifest:
        safe = resolve_within_root(root, m.path)
        dest = snap_dir / Path(m.path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe, dest)
    manifest_payload = {
        "snapshot_id": snapshot_id,
        "source_id": source.source_id,
        "files": [
            {
                "path": m.path,
                "content_hash": m.content_hash,
                "size_bytes": m.size_bytes,
                "is_markdown": m.is_markdown,
                "capability": m.capability,
            }
            for m in manifest
        ],
    }
    (snap_dir / "manifest.json").write_text(
        json.dumps(manifest_payload, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return SnapshotResult(source.source_id, snapshot_id, tuple(manifest),
                          tuple(findings), created=True)


def _manifest_hash(manifest: list[SnapshotFile]) -> str:
    h = hashlib.sha256()
    for m in manifest:
        h.update(f"{m.path}\x00{m.content_hash}\x00{m.size_bytes}\x00".encode())
    return h.hexdigest()[:32]
