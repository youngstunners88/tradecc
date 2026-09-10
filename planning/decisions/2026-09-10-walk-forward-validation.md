# Decision: Walk-Forward Validation Protocol (2026-09-10)

## Context

The cost-model correction
(`research/backtests/2026-09-10_cost-model-correction.md`) moved the 1h
Stage-5 backtest from −$0.12 to +$0.58 at default parameters. That result
is **not** established: it sits inside the sensitivity band of the one
slippage component still assumed, and the 2026-09-09 held-out slice it
would otherwise be checked against has been scored and is spent.

Re-scoring a spent held-out slice against a changed cost model is not
out-of-sample validation — it is a second look at data whose answer is
known. So a fresh evaluation protocol is fixed here, **before it is
built**, so it cannot quietly become "search until the corrected number
replicates."

This record is written before the harness exists and before any fold has
been scored. The only thing inspected beforehand is trade count per
candidate window — a property of the data, not of any result — recorded
below because it determines the fold count.

## Why walk-forward, not fresh data

A calendar day of new candles adds ~24 1h bars — too few to validate
against, and waiting days to accumulate enough delays the answer without
improving the method. Walk-forward reuses the history already cached, in
a way that never scores a window that influenced the parameters producing
its trades. For Phase A there are no such parameters (defaults
throughout), so walk-forward there is purely a **temporal consistency
check**: does the corrected-cost result hold across sub-periods, or does
it live in one stretch of the series?

## Fold structure (fixed in advance)

**Expanding window, 3 folds.** Chosen over rolling because:

- At 41 days of 1h history, discarding early bars (as a rolling window
  does) is unaffordable.
- Expanding matches how the bot would actually operate — retrain on all
  history to date.
- A rolling window introduces a window-length parameter, which is one
  more knob available to overfit.

The cost of expanding is that later folds train on more data than earlier
ones, so folds are not comparable on the *train* side. Acceptable here:
what is compared is the **test-side** result, and test windows are equal
in length.

**3 folds, not 5** — driven by measured trade counts, not preference. At
default parameters over each full series:

| Interval | Trades | 3-fold split | 5-fold split |
|---|---|---|---|
| 1h | 15 | [4, 7, 4] | [2, 4, 4, 3, 2] |
| 4h | 21 | [8, 5, 8] | [7, 2, 3, 5, 4] |
| 15m | 23 | [8, 6, 9] | [5, 3, 5, 4, 6] |

At 5 folds the 1h folds fall to 2 trades, where a single trade flips the
sign. 3 folds holds the minimum at 4. Still small — see the honesty
caveat below.

**Intervals: 1h, 4h, 15m. 1d is excluded** — 4 trades across 183 days,
folds of 0–2 trades. Nothing is learnable from it, and including it only
adds a chance to get lucky.

## Phase A — baseline, no search (built and run first)

No parameter search at all. Default parameters
(`fast_ema=12, slow_ema=26, rsi_period=14, rsi_overbought=70`) everywhere.

1. Split each series into **3 consecutive equal-length windows** by
   candle index, tiling the whole series.
2. Score each trade in the fold its **entry** falls in. Because Phase A
   holds parameters fixed, a single causal backtest over the whole series
   produces exactly the trades each expanding fold would; bucketing those
   trades by entry timestamp is equivalent and is how Phase A is
   computed. (Phase B, which does search, cannot take this shortcut and
   will run each fold's train/test separately.)
3. Warmup for a trade comes from the candles preceding its window, exactly
   as it would live — the first ~27 bars of fold 0 are warmup, not
   tradeable, which is expected.
4. Report **every fold's** net, gross, fees, trade count, and win rate.
   Never the best fold alone.

Phase A answers one question: does the corrected-cost result replicate
across time, at the parameters that produced it?

## Decision rule (locked, applies to the 1h +$0.58 result)

"Replicated" requires **all** of:

1. Net > 0 in **≥ 2 of 3** folds.
2. **Pooled** out-of-sample net > 0.
3. No single fold contributes **> 60%** of pooled net (one stretch
   carrying the result is the failure mode being tested for).
4. Pooled trade count **≥ 12**.

**Any** failure → the result **did not replicate**. Write that up plainly
and stop. Do not widen the grid, add indicators, change the fold count,
or search for parameters that make it replicate — each is fitting the
validation by hand, and the correct output of a failed check is the
finding that it failed.

## Phase B — search (only if Phase A is greenlit afterwards)

Not built or run until Phase A's result is reported and the user
explicitly approves proceeding. When it runs: initial train = first 40%
of each series; 3 expanding test folds over the remaining 60%; grid
searched on train only; exactly one configuration per fold, scored once,
no re-picking. Same decision rule.

## What this record forecloses

- Re-scoring the spent 2026-09-09 held-out slice as though out-of-sample.
- Changing the fold count, interval set, or decision rule after seeing a
  result.
- Running Phase B before Phase A is reported and approved.
- Reporting the best fold, or a pooled number, without every fold beside
  it.
- Treating replication as gate-clearing. The live gate additionally
  requires 30 days of paper trading and a pre-set drawdown threshold; a
  replicated backtest is necessary, never sufficient.

## Honesty caveat carried into every report

4–8 trades per fold detects gross inconsistency and nothing finer. A pass
means "not refuted at this sample size", never "confirmed". No arithmetic
in this protocol turns 15 trades into statistical significance, and no
report produced under it may imply otherwise.
