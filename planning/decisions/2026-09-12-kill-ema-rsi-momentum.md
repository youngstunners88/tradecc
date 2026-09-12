# Decision: Close the v0.1 EMA/RSI momentum path — no demonstrated edge

**Date:** 2026-09-12
**Status:** Closed. No further tuning. No Stage 6 live execution for this
strategy. `live` mode stays locked.

## Verdict

**EMA/RSI momentum on SOL/USDC has no demonstrated edge at $5–$10 position
sizes under the corrected cost model.** Six independent tests, each run under a
protocol fixed in advance, converge on the same answer. The strategy also loses
to buy-and-hold on every interval measured.

This record closes the path. It does not delete the code: the strategy module,
the backtest runner, the risk engine and the paper trader are all reusable
infrastructure, and the one thing this exercise *did* produce is a validation
apparatus that reliably says no.

## The evidence

| Round | Method | Result |
|---|---|---|
| Sweep + holdout (2026-09-09) | 144 combos × 3 intervals, 70/30 chronological split fixed in advance | 1h tuning **+$0.86 → held-out −$0.66**; 4h +$0.47 on **3 trades**; 1d no eligible config; **78–88% of the tuning space lost money** on the range it was tuned on |
| Cost-model correction (2026-09-10) | Four bad cost inputs found and fixed against live APIs | 1h moved to **+$0.58**, but **crosses zero at ~0.29%/side** execution slippage — inside one assumption's sensitivity band. 15m negative across the entire band |
| Walk-forward Phase A (2026-09-10) | Expanding window, 3 folds, default parameters | 1h pooled +0.5815 but **concentration FAIL** (folds 1 and 2 are 82% and 75%); 4h pooled **−0.4264** (re-measured −0.5494); 15m **−1.7785**, negative in all three folds |
| Walk-forward Phase B (2026-09-10) | Same folds, grid searched per fold on train only | **No interval replicates.** Pooled out-of-sample trade counts **10 / 7 / 10**, all below the pre-committed floor of 12. The search picked a different configuration every fold |
| Cross-sectional momentum (2026-09-12) | 5-token universe, $10 total, 6-combination grid, all reported | **All six fail.** Top row `L=7,N=1` returned +$13.4381 — **94% of it from a single fold**. The folds track a broad rally, not a ranking rule |
| Regime pre-registration (2026-09-12) | Step-4 mechanism check at default parameters | **Trend arm empty — 1 trade in 59** entered a trend-labelled bar. Kills the mechanism-level explanation, not just the P&L |

**Buy-and-hold, the baseline our own protocol required and which went
uncomputed until 2026-09-11, beats the strategy everywhere:**

| Window | Strategy | Buy-and-hold |
|---|---|---|
| 1h | +$0.58 | **+$3.93** |
| 4h | −$0.55 | **+$1.70** |
| 15m | −$1.78 | **−$0.28** |

Full write-ups in `research/backtests/`.

## What this forecloses

- **No further EMA/RSI parameter tuning on this pair.** The distribution is
  mostly negative; taking its maximum is selection bias, which the sweep and
  Phase B both demonstrated directly.
- **No Stage 6 live-execution work for this strategy.** Building a signing and
  transaction-sending path — the most dangerous code in this project — on top
  of a signal with no positive expectancy is negative-EV by construction.
- **`live` mode stays locked.** Unchanged: the validation gate in
  `planning/specs/mvp_spec.md` still governs, and it is additionally
  **incomplete** — no decision record has ever set the max-drawdown threshold
  it requires, so the gate could not be cleared today even by a strategy that
  worked.
- **Re-opening requires new evidence, not a new opinion.** A material flaw
  found in the six results or in the buy-and-hold baseline reopens this. A
  preference for the strategy does not.

## What it does not foreclose

Cross-sectional momentum **as a class** is not disproven. One regime and a
five-token universe cannot support that claim — the limitation is recorded in
`planning/decisions/2026-09-12-cross-sectional-momentum-protocol.md` and is
load-bearing here. "This data cannot support the claim" is a weaker and more
honest statement than "the effect is absent."

## The remaining named question

Copy-trading / wallet-following (v0.2) is the only named, untested signal
source in scope:

> Can following a pre-vetted set of Solana wallets produce positive net
> expectancy at $5–$10 after the corrected cost model, with ≥ 12 out-of-sample
> trades and no fold contributing > 60% of pooled net?

**Not measured.** It requires its own pre-registered decision record before any
code is written, per the standing rule that protocols are fixed before data is
touched. If no data source with sufficient wallet history and depth exists,
then there is no remaining research question capable of producing a tradeable
edge under current constraints — and that conclusion should be written down
rather than avoided.

## Note on scope of this record

This record documents and stops. It adds no code, removes no safety control,
and changes no risk parameter. The validation gate, the circuit breaker, the
position-size default and all seven CLAUDE.md rules are untouched.
