"""Path confinement for vault sources (A14-1 security doctrine).

Every filesystem access during ingestion goes through `resolve_within_root`:
a candidate relative path must stay inside the registered source root both
textually (after normalisation, which kills `..` traversal) and physically
(after symlink resolution, which kills symlink escapes). A path that fails
either check raises `PathEscapeError` *before* any content is read — the
caller never receives a readable handle to outside material.

This is a unit-level guard, not a sandbox: it pins the path-resolution step
of the ingest pipeline. TOCTOU races on a live filesystem are out of scope
here and are why parsing always reads from the immutable snapshot, never
from the live source tree.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

REASON_TRAVERSAL = "dotdot_traversal"
REASON_ABSOLUTE = "absolute_path"
REASON_OUTSIDE_ROOT = "outside_root"
REASON_SYMLINK_ESCAPE = "symlink_escape"


class PathEscapeError(Exception):
    """A path attempt left the registered source root.

    `reason` is one of the ``REASON_*`` constants so callers can surface a
    visible, classified error record (never a silent drop).
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def resolve_within_root(root: Path, relative: str | Path) -> Path:
    """Resolve ``relative`` under ``root`` or raise ``PathEscapeError``.

    Checks, in order (all before any read):

    1. ``relative`` must be a relative POSIX-ish path with no ``..`` component
       and no drive/anchor — rejects ``../outside.md``, ``a/../../x``, and
       absolute paths outright.
    2. Textual containment: ``normpath(root / relative)`` must stay under the
       normalised root — a second traversal net (e.g. via doubled separators).
    3. Physical containment: the fully symlink-resolved candidate must stay
       under the resolved root — a symlink inside the vault pointing outside
       is an escape, and the resolved path is never returned to the caller.
    """
    root_n = Path(root).resolve()

    pure = PurePosixPath(str(relative).replace("\\", "/"))
    if pure.is_absolute() or pure.drive or pure.root:
        raise PathEscapeError(
            REASON_ABSOLUTE, f"absolute paths are not valid inside a source: {relative!r}"
        )
    parts = pure.parts
    if ".." in parts:
        raise PathEscapeError(
            REASON_TRAVERSAL, f"'..' traversal rejected outside root: {relative!r}"
        )
    rel = PurePosixPath(*[p for p in parts if p not in (".",)])

    # Textual containment against the lexically normalised root (no symlink
    # following). normpath collapses `a/../b` so a traversal net that survived
    # the parts check is still caught here.
    textual = Path(root_n, *rel.parts)
    textual_norm = Path(os.path.normpath(textual))
    root_norm = Path(os.path.normpath(root_n))
    if not _is_within(textual_norm, root_norm):
        raise PathEscapeError(
            REASON_OUTSIDE_ROOT, f"path normalises outside the source root: {relative!r}"
        )

    # Physical containment: resolve symlinks and re-check. strict=False so a
    # not-yet-existing destination is still classified correctly.
    resolved = textual.resolve()
    if not _is_within(resolved, root_n):
        raise PathEscapeError(
            REASON_SYMLINK_ESCAPE,
            f"symlink escape rejected (resolves outside root): {relative!r} -> {resolved}",
        )
    return resolved


def symlink_escape_target(root: Path, candidate: Path) -> Path | None:
    """Return the outside-root target when ``candidate`` is a escaping symlink.

    Used by the snapshot walker to classify symlinked entries without reading
    their content: the returned path is only ever compared, never opened.
    """
    root_n = Path(root).resolve()
    resolved = candidate.resolve()
    if not _is_within(resolved, root_n):
        return resolved
    return None


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True
