# Walk-Forward Phase B — search over an initial train block, SOL/USDC

**Date:** 2026-09-10
**Protocol:** `planning/decisions/2026-09-10-walk-forward-validation.md`.
Phase B was run only after Phase A was reported and the user approved
proceeding.
**Method:** initial train = first 40% of each series; 3 expanding test
folds over the remaining 60%. Each fold searched the 144-combination grid
on everything before its test window, selected one configuration by the
sweep's rule (max net expectancy on train, ≥10 trades), and scored it on
the test window exactly once. No re-picking.

## Verdict

**No interval replicates. Searching for the best per-fold parameters did
not rescue the strategy — it produced weaker evidence, not stronger.**
Per the stopping rule fixed in advance, this is the end of the line for
tuning this strategy.

Two structural facts sink it:

1. **Trade counts collapsed below the floor.** A test fold is 20% of the
   series, so pooled out-of-sample trade counts were **10, 7, and 10** —
   all below the pre-committed minimum of 12. Out-of-sample evidence this
   thin cannot support any conclusion, in either direction.
2. **The search chose a different configuration every fold**, several of
   them the noise-shaped near-adjacent EMAs the sweep already flagged
   (`f20/s21`). A strategy whose "best" parameters are unstable across
   adjacent time windows has not found an edge; it has fit each window's
   noise.

## Results — every fold, per the protocol

### 1h — 1000 candles, 2026-07-29 → 2026-09-09

| Fold | Test window | Chosen on train | Trades | Net |
|---|---|---|---|---|
| 0 | 08-15 → 08-23 | f8 / s21 / r21 / ob70 | 6 | +0.3042 |
| 1 | 08-23 → 09-01 | f5 / s50 / r21 / ob80 | 2 | +0.8061 |
| 2 | 09-01 → 09-09 | f20 / s21 / r21 / ob70 | 2 | +0.2042 |
| **pool** | | | **10** | **+1.3145** |

Rule: majority-positive PASS, pooled-positive PASS, **concentration FAIL**
(fold 1 is 61% of pooled, on 2 trades), **trades FAIL** (10 < 12).
**Replicated: NO.** The pooled positive rides on a single 2-trade fold.

### 4h — 1000 candles, 2026-03-27 → 2026-09-09

| Fold | Test window | Chosen on train | Trades | Net |
|---|---|---|---|---|
| 0 | 06-01 → 07-04 | f5 / s26 / r7 / ob70 | 3 | +0.8671 |
| 1 | 07-05 → 08-07 | f12 / s34 / r21 / ob80 | 2 | −0.3620 |
| 2 | 08-07 → 09-09 | f20 / s34 / r7 / ob80 | 2 | +0.2834 |
| **pool** | | | **7** | **+0.7885** |

Rule: majority-positive PASS, pooled-positive PASS, **concentration FAIL**,
**trades FAIL** (7 < 12). **Replicated: NO.** Seven out-of-sample trades
across 5.5 months is not evidence.

### 15m — 1000 candles, 2026-08-30 → 2026-09-09

| Fold | Test window | Chosen on train | Trades | Net |
|---|---|---|---|---|
| 0 | 09-03 → 09-05 | f5 / s26 / r7 / ob70 | 5 | −0.2209 |
| 1 | 09-05 → 09-07 | f12 / s21 / r7 / ob70 | 3 | −0.2319 |
| 2 | 09-07 → 09-09 | f5 / s21 / r7 / ob60 | 2 | −0.1854 |
| **pool** | | | **10** | **−0.6383** |

Rule: every condition FAIL. **Replicated: NO.** Negative in all three
folds even after per-fold optimisation.

## What Phase B adds over Phase A

Phase A showed the default-parameter result did not replicate. Phase B
asked the stronger question — does *any* fixed parameter set, chosen
honestly on past data, survive out-of-time? — and the answer is no. The
per-fold winners disagree with each other, the out-of-sample samples are
too small to trust, and the one interval that was net-negative at defaults
(15m) stays net-negative even when each fold is optimised in its own
favour.

This is the fourth converging negative: the original sweep, the
cost-corrected re-run, Phase A, and now Phase B. They do not each add
independent information — they are the same finding seen four ways — but
together they close off the "we just haven't found the right parameters"
hypothesis under a protocol fixed in advance.

## What was deliberately not done

The grid was not widened, no indicators were added, no interval was added
back, no fold was re-scored, and no configuration was picked after seeing
its test result. Each would have been fitting the validation by hand.

## Honesty caveat

Phase B's out-of-sample folds are smaller than Phase A's (2–6 trades) and
correspondingly weaker. That cuts both ways: it means a *pass* here would
have been very weak evidence, and it means the failure is partly a
sample-size failure, not only a performance one. The protocol anticipated
this — the ≥12-trade condition exists precisely so a lucky 2-trade fold
cannot be reported as replication.

## Recommendation

Stop tuning EMA/RSI momentum on SOL/USDC at these sizes. The evidence
does not support it, and the protocol's whole point was to make "stop" a
respectable outcome rather than a reason to search harder. Genuinely new
directions (a different signal source such as the v0.2 copy-trading work,
or a different market regime filter) are decisions for the user under a
fresh decision record — not a continuation of this search.

---

## Addendum — 2026-09-11: re-measured against the fixed harness

The point-in-time audit of 2026-09-11 fixed three defects in the
backtest/paper path (commit `bd1f7fc`) — decisions stamped at the bar's
open while using its close, stops evaluated on the close only with
`high`/`low` never read, and paper mode acting on the still-forming bar.
See
`research/backtests/2026-09-11_momentum_lookahead-audit-and-buy-hold-baseline.md`.

Phase B was re-run in full against the fixed harness. **The figures above
are left as originally published**; this addendum records what changed.

| Interval | Pooled, published | Pooled, re-run | Trades | Verdict |
|---|---|---|---|---|
| 1h | +1.3145 | **+1.2929** | 10 (unchanged) | still NO |
| 4h | +0.7885 | **+1.1498** | 7 (unchanged) | still NO |
| 15m | −0.6383 | **−0.6383** | 10 (unchanged) | still NO |

Per-fold, only two numbers moved: 1h fold 1 (+0.8061 → +0.7845) and 4h
fold 1 (−0.3620 → **−0.0007**). 15m is bit-identical throughout.

**A second-order effect worth recording.** On 4h fold 1 the *selected
configuration itself changed*, from `f12/s34/r21/ob80` to
`f12/s34/r7/ob80`. The intrabar-stop fix altered results on the training
slice, which changed which configuration won the search. The fix
propagates through parameter selection, not only through P&L — which is
why this was re-run rather than assumed.

Note the direction differs from Phase A: 4h improves here (+0.79 →
+1.15) while Phase A's 4h worsens (−0.43 → −0.55). Not a contradiction —
Phase A trades fixed defaults, Phase B trades searched parameters, and
the fix changed which parameters fold 1 selected.

**No verdict changes.** All three intervals still fail the locked
replication rule, and they fail on the structural conditions the extra
P&L cannot touch: pooled trade counts remain 10, 7 and 10 against a
floor of 12, and every interval still fails concentration. A larger
pooled number on seven out-of-sample trades is not evidence of an edge —
it is the same too-small sample, slightly rearranged.
