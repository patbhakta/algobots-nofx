"""NoFX <-> Nautilus order bridge (ALG-3340, ALG-3339 microsprint 3).

Law (ADR 0001): every order and fill goes through a Nautilus
``ExecutionClient``. This package is the control-plane half of the bridge —
it admits intents and owns the shared file channel — but it never simulates
a fill: execution happens on the account's paper worker
(``engine.workers.paper``) and its ``OrderFilled`` events are mirrored to
``bridge/fills/`` JSONL by that worker, never by the API process.
"""
