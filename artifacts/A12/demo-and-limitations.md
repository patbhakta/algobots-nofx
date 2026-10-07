# A12 / G1 walkthrough — demo and limitations (ALG-3257)

Run: `uv run --extra workers make demo-g1` (needs node + playwright-core for
the screenshots). Green run 2026-10-07: 5/5 capabilities in ~52 s on this VPS.

- What the run proves, capability by capability: `docs/gates/G1/decision.md`
  (the gate call: proven / simulated / blocked / failed).
- Timeline + trace IDs + denial records: `demo-run.json`.
- App-level resource report (1 Hz `/proc` sampling): `resource-report.json`;
  engine-level kill/restart/reconcile + measurements: `engine/`.
- Screenshots: `demo-1440.png`, `demo-390.png` (walkthrough card open).

Limitations (stated, not hidden): synthetic feed standing in for Laya/Kalshi;
fills at the assumed 0.50 mid + Kalshi taker fee on the Nautilus paper venue;
the app does not auto-restart a killed worker (restart-with-reconciliation is
proven at the engine layer); the strategies have no edge and nothing here
measures profitability; no fleet capacity is inferred from one host.

Descope record (A12-2, ALG-3303): original A12 AC3–AC5 — the knowledge
importer (source anchor + tenant scope), the DecisionModel/Jev mock + live
smoke, and the invalid-answer shadow REVIEW/ABSTAIN path — are descoped per
Pat's Oct 6 functional-terminal ruling and redirected to A14 (ALG-3110) /
A17 (ALG-3113) / A18 (ALG-3114). See `docs/gates/G1/decision.md` (Blocked)
and `acceptance.json` (DESCOPED statuses).
