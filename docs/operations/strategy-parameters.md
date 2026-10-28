# Strategy cards and parameter editing

Open Strategy Studio, choose **Add strategy**, then select Laya, Coinflip, or Jev. The new saved card opens its parameters immediately. Edit and save, select a frozen recorder snapshot in Backtest, and inspect the resulting evidence. Cards remain selectable on small screens. A failed create leaves the picker available to retry.

- **Laya:** minimum absolute edge from 50%, in [0, 0.5]. Replay recomputes momentum from prior settled closes. This typed value takes precedence over legacy `demo_worker.min_edge`.
- **Coinflip:** entry delay of 0–899 seconds after market open and a positive decimal USD stake. SHA256(event)'s low bit fixes the pick, independently of the outcome. Replay enters only if the captured observation falls at or after that delay and before close. A snapshot containing only earlier observations abstains; it cannot recreate a later book.
- **Jev:** minimum confidence in [0, 1]. Replay needs `jev_choice`, `jev_p`, `jev_conf`, and `jev_ts` on the recorded row. The call timestamp must lie between market open and the captured observation, and that observation must precede close. Missing or insufficient-confidence calls abstain. This performs no inference or paid API calls.

The recorder replay retains its existing paper execution assumptions: recorded book when available, otherwise an explicitly reported assumed 50c price, demo fees, and the frozen risk envelope. These results are simulated returns, not observed trading P&L. Jev snapshots without timestamped calls will show zero fills. OHLC bar snapshots are refused for recorder baselines.

`baseline` is a strict discriminated parameter object on the NoFX config and Studio draft. Unknown strategies, extra fields, invalid ranges, noninteger delays, and nonstring money values fail compilation with a field error. Valid saves append immutable artifacts. Changing parameters changes the artifact hash and requires fresh evidence; existing artifacts and running workers remain frozen. Drafts without `baseline` retain their previous hashes.

The three recorder implementations support research replay. They have no deployment worker through the Studio deployment API (which currently accepts condition DSL artifacts); the UI states this before offering deployment. Saving or activating a configuration does not reconfigure the shared paper loop. This change does not deploy a new application image.
