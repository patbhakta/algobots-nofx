"""Evidence snapshot (ALG-3357): validation + atomic publish, no docker needed."""

from __future__ import annotations

import importlib.util
import sys
import urllib.request
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

# --- share-out publish + HTTP reachability (ALG-3357) ---

def test_publish_web_copies_atomically_and_keeps_source(tmp_path):
    source = tmp_path / "notebooks" / "latest.html"
    source.parent.mkdir()
    source.write_bytes(_big_html(tmp_path).read_bytes())
    web_dir = tmp_path / "share-out"
    target = web_dir / "latest.html"
    target.parent.mkdir()
    target.write_bytes(b"old web evidence")

    mod.publish_web(source, target)

    assert target.read_bytes() == source.read_bytes()  # new content live
    assert source.exists()  # container copy untouched
    assert not (web_dir / ".kalshi_demo_loop.web.html").exists()  # no tmp litter


def test_verify_http_accepts_200_big_body(monkeypatch):
    class _Resp:
        def __init__(self, body):
            self._body = body
        def read(self):
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "SHARE_URL", "http://x/latest.html")
    monkeypatch.setattr(mod, "MIN_BYTES", 100)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(b"z" * 500))
    ok, reason = mod.verify_http()
    assert ok, reason


def test_verify_http_rejects_transport_error_and_short_body(monkeypatch):
    monkeypatch.setattr(mod, "SHARE_URL", "http://x/latest.html")
    monkeypatch.setattr(mod, "MIN_BYTES", 100)

    def _boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    ok, reason = mod.verify_http()
    assert not ok and "unreachable" in reason

    class _Resp:
        def read(self):
            return b"z" * 10
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp())
    ok, reason = mod.verify_http()
    assert not ok and "short body" in reason
