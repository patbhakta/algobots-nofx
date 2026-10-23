"""Evidence snapshot (ALG-3357): validation + atomic publish, no docker needed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "evidence_snapshot",
    Path(__file__).resolve().parents[2] / "src/algobots/demo/evidence_snapshot.py",
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["evidence_snapshot"] = mod
_spec.loader.exec_module(mod)


def _big_html(tmp_path: Path) -> Path:
    p = tmp_path / "snap.html"
    blob = b"<html>kalshi demo " + b"x" * 60_000 + b"marimo_version" + b"</html>"
    p.write_bytes(blob)
    return p


def test_valid_snapshot_passes(tmp_path):
    ok, reason = mod.validate_snapshot(_big_html(tmp_path))
    assert ok, reason


def test_small_or_markerless_export_rejected(tmp_path):
    small = tmp_path / "small.html"
    small.write_bytes(b"kalshi marimo_version")  # has markers, too small
    ok, _ = mod.validate_snapshot(small)
    assert not ok

    wrong = tmp_path / "wrong.html"
    wrong.write_bytes(b"x" * 60_000)  # big enough, no notebook markers
    ok, _ = mod.validate_snapshot(wrong)
    assert not ok

    ok, _ = mod.validate_snapshot(tmp_path / "missing.html")
    assert not ok


def test_publish_is_atomic_replace_and_failure_keeps_old(tmp_path):
    published = tmp_path / "latest.html"
    published.write_bytes(b"old evidence")
    snap = _big_html(tmp_path)
    mod.publish(snap, published)
    assert published.read_bytes().endswith(b"</html>")
    assert not snap.exists()  # replaced, not copied
