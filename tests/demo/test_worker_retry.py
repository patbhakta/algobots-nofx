"""ALG-3308 follow-up: denied demo accounts self-heal via the sync-loop retry.

Replays today's incident: recreating the API container leaves its workers'
leases with an unprobeable generation whose heartbeats were fresh *seconds*
before the old container died — correctly denied at startup. Without a retry
the demo then ran with zero engines until a manual restart. The retry must
keep denying while the heartbeat is fresh and recover exactly when the
silence window proves the holder gone.
"""

import json
import os
import sys
import time
from pathlib import Path

from algobots.engine.workers import lease as LS
from algobots.engine.workers.lease import Lease

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine" / "workers"))
from test_supervisor import _supervisor, _wait  # noqa: E402

from algobots.demo.router import retry_denied_workers  # noqa: E402


def _plant_old_generation(
    tmp_path, account: str, *, acquired_ago: float, heartbeat_ago: float | None
):
    ls = Lease(tmp_path, account)
    ls.path.parent.mkdir(parents=True, exist_ok=True)
    ls.path.write_text(json.dumps(
        {**LS.identity(os.getpid()), "pidns": "pid:[1]", "acquired_at": time.time() - acquired_ago}
    ))
    hb = tmp_path / "workers" / f"{account}.json"
    hb.parent.mkdir(parents=True, exist_ok=True)
    if heartbeat_ago is not None:
        hb.write_text(json.dumps({"pid": 1, "last_heartbeat": time.time() - heartbeat_ago}))


def test_denied_account_recovers_on_retry_after_silence(tmp_path):
    # recreation race: lease old, but the dead generation heartbeat is FRESH
    _plant_old_generation(tmp_path, "laya", acquired_ago=3600, heartbeat_ago=5)
    sup = _supervisor(tmp_path)
    try:
        sup.start()  # raises past the denied accounts, but starts the free ones
    except Exception:
        pass
    assert "laya" in sup.denied, "fresh heartbeat must keep the lease denied"

    # retry while the heartbeat is still fresh: still denied, nothing recovered
    assert retry_denied_workers(sup) == []
    assert "laya" in sup.denied

    # the generation goes silent past the stale window: retry reclaims + starts
    hb = tmp_path / "workers" / "laya.json"
    hb.write_text(json.dumps({"pid": 1, "last_heartbeat": time.time() - 900}))
    assert retry_denied_workers(sup) == ["laya"]
    assert "laya" not in sup.denied
    assert _wait(lambda: sup.status("laya").state == "ready")
    assert "laya" in sup.reclaimed
    assert sup.status("laya").denied_reason is None
    sup.stop()

    # a healthy supervisor with no denials is a no-op
    assert retry_denied_workers(sup) == []


def test_retry_is_noop_without_denials_or_supervisor(tmp_path):
    sup = _supervisor(tmp_path)
    try:
        assert retry_denied_workers(sup) == []  # nothing denied, nothing attempted
    finally:
        sup.stop()
    assert retry_denied_workers(None) == []
