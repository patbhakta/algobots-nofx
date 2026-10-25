"""Run inside UID-1000 quantlab; consumes an existing snapshot without publishing."""

import copy
import json
import sys
from pathlib import Path

from algobots.strategies.ohlc import run
from algobots.warehouse import Warehouse

artifact = json.loads(Path(sys.argv[1]).read_text())
snapshot = sys.argv[2]
manifest, table = Warehouse(Path("/home/quantlab/openbb_store")).load(snapshot)
rows = table.to_pylist()
base = run(artifact, manifest, rows)
assert base["engine"]["iterations"] == len(rows)
assert base["trades"]
assert all(float(t["event"]) / 1e9 > t["signal_ts"] for t in base["trades"])
assert all(
    float(t["qty"]) * float(t["price"])
    <= float(artifact["nautilus"]["risk_envelope"]["max_order_value"])
    for t in base["trades"]
    if t["side"] == "BUY"
)
altered = copy.deepcopy(rows)
altered[-1]["open"] *= 2
altered[-1]["high"] *= 2
altered[-1]["low"] *= 2
altered[-1]["close"] *= 2
changed = run(artifact, manifest, altered)
cutoff = rows[-1]["timestamp"]
assert [t for t in base["trades"] if float(t["event"]) / 1e9 < cutoff] == [
    t for t in changed["trades"] if float(t["event"]) / 1e9 < cutoff
]
disabled = copy.deepcopy(artifact)
disabled["spec"]["entry"]["right"]["value"] = 1e9
assert not run(disabled, manifest, rows)["trades"]
capped = copy.deepcopy(artifact)
capped["nautilus"]["risk_envelope"]["max_order_value"] = "0.01"
assert not run(capped, manifest, rows)["trades"]
print(
    json.dumps(
        dict(
            snapshot_id=snapshot,
            sha256=manifest["sha256"],
            executor=base["executor"],
            metrics=base["metrics"],
            trades=base["trades"],
            prior_bar_signals=True,
            future_mutation_invariant=True,
            false_entry_no_fills=True,
            order_cap_enforced=True,
        ),
        sort_keys=True,
    )
)
