# Walk-Forward Phase A — baseline, momentum, SOL/USDC

**Date:** 2026-09-10
**Protocol:** `planning/decisions/2026-09-10-walk-forward-validation.md`,
fixed before the harness was built.
**Parameters:** defaults (`fast_ema=12, slow_ema=26, rsi_period=14,
rsi_overbought=70`), corrected cost model. No search.

## Verdict

**The corrected-cost 1h result did not replicate. Neither did 4h or 15m.**
Per the stopping rule fixed in advance, the search stops here — no grid
widening, no parameter hunt, no Phase B unless the user directs it.

The +$0.58 that the cost correction produced on 1h is real arithmetic,
but it is **carried by the back two-thirds of the series while the
earliest third loses money.** That is exactly the concentration the
decision rule was written to catch, and it caught it.

## Results — every fold, not the best one

### 1h — 1000 candles, 2026-07-29 → 2026-09-09

| Fold | Window | Trades | Gross | Fees | Net | Win% |
|---|---|---|---|---|---|---|
| 0 | 07-29 → 08-12 | 4 | −0.1458 | 0.1874 | **−0.3332** | 25.0 |
| 1 | 08-12 → 08-26 | 7 | +0.5511 | 0.0715 | **+0.4796** | 28.6 |
| 2 | 08-26 → 09-09 | 4 | +0.4866 | 0.0514 | **+0.4351** | 75.0 |
| **pool** | | 15 | | | **+0.5815** | |

| Rule | Result |
|---|---|
| net > 0 in ≥ 2/3 folds | PASS (2/3) |
| pooled net > 0 | PASS |
| no fold > 60% of pooled net | **FAIL** — folds 1 and 2 are 82% and 75% |
| pooled trades ≥ 12 | PASS (15) |
| **Replicated** | **NO** |

The whole-series positive is not spread across time. Fold 0 — the first
two weeks — loses money outright, and either of the other two folds alone
exceeds the entire pooled net. A result that depends on which fortnight
you start in is not an edge; it is a period.

### 4h — 1000 candles, 2026-03-27 → 2026-09-09

| Fold | Window | Trades | Gross | Fees | Net | Win% |
|---|---|---|---|---|---|---|
| 0 | 03-27 → 05-21 | 8 | −1.1211 | 0.2555 | **−1.3766** | 25.0 |
| 1 | 05-21 → 07-15 | 5 | +0.8753 | 0.0472 | **+0.8281** | 40.0 |
| 2 | 07-16 → 09-09 | 8 | +0.2049 | 0.0828 | **+0.1221** | 37.5 |
| **pool** | | 21 | | | **−0.4264** | |

| Rule | Result |
|---|---|
| net > 0 in ≥ 2/3 folds | PASS (2/3) |
| pooled net > 0 | **FAIL** (−0.43) |
| no fold > 60% of pooled net | **FAIL** (pooled is negative) |
| pooled trades ≥ 12 | PASS (21) |
| **Replicated** | **NO** |

This is the more important 4h finding: **over the full 5.5 months, 4h is
net negative at default parameters.** The sweep's +$0.47 held-out 4h
number came from *tuned* parameters on 3 trades; at defaults across a long
window, 4h loses. Two of three folds are positive, but a single bad
early fold outweighs both.

### 15m — 1000 candles, 2026-08-30 → 2026-09-09

| Fold | Window | Trades | Gross | Fees | Net | Win% |
|---|---|---|---|---|---|---|
| 0 | 08-30 → 09-02 | 8 | −0.3882 | 0.3169 | **−0.7051** | 12.5 |
| 1 | 09-02 → 09-06 | 6 | −0.0153 | 0.0768 | **−0.0920** | 50.0 |
| 2 | 09-06 → 09-09 | 9 | −0.8640 | 0.1173 | **−0.9814** | 0.0 |
| **pool** | | 23 | | | **−1.7785** | |

Negative in all three folds. This conclusion was already robust in the
cost-correction write-up and is unchanged.

## What this means

- **The cost correction was still worth doing.** It fixed four real
  errors and made the model materially more accurate. It did not create
  an edge — it removed a distortion that made one interval briefly look
  like it had one.
- **The 1h "sign flip" was a mirage twice over.** First, it sat inside
  the sensitivity band of the assumed slippage component. Second, and
  independently, the positive whole-series number is a concentration
  artefact — remove the luckiest fold and it is gone.
- **Default-parameter momentum on SOL/USDC has no demonstrable edge** at
  1h, 4h, or 15m at $10 sizes, across every window tested. This now rests
  on out-of-time folds, not a single backtest.

## What was deliberately not done

Per the decision record: the grid was not widened, no indicators were
added, the fold count and interval set were not changed after seeing
results, and no parameter search was run to make the result replicate.
Phase B (search over an initial train block) is defined in the record but
was not built or run — it awaits an explicit decision after this report.

## Honesty caveat

4–8 trades per fold detects gross inconsistency and nothing finer. These
folds "not replicating" is a strong negative signal precisely because the
result failed even the coarse check; a *pass* here would not have been
proof of an edge, only failure-to-refute. Nothing in this protocol makes
15 trades statistically significant.

## Recommended next step

The evidence across the sweep, the cost correction, and now
walk-forward points one direction: **default-parameter EMA/RSI momentum
does not have an edge on this pair at these sizes.** The honest options
are (a) accept that and stop tuning this strategy, or (b) run Phase B as a
last, protocol-bound check on whether *any* fixed parameter set survives
out-of-time — with the expectation, given three converging negatives,
that it will not. Either is the user's call. Continuing to tune without a
fixed protocol is the one option the evidence rules out.
