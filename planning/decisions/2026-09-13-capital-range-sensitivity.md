# Decision: Capital-range sensitivity — the interpretation rule, fixed before the numbers

**Date:** 2026-09-13
**Status:** Rule locked. No result has been computed at the time of writing.

## The question

One of three paths under consideration is raising the capital range. The
honest version of that question is not "would bigger positions make more
money" — of course a positive return scales — but:

> **Do any of the six recorded negatives flip positive at larger size, and if
> so, does the flip track the fee curve?**

Fixed costs per round trip are ~$0.0127 recurring, so the cost hurdle falls as
size rises:

| Size | Hurdle per round trip |
|---|---|
| $5 | 0.47% |
| $10 | 0.35% |
| $25 | 0.27% |
| $100 | 0.23% |

That curve is the whole test. It is written here **before any re-run**, because
the temptation this exercise creates is obvious: run four sizes, find one
positive number, and call it a capital problem.

## The interpretation rule (locked)

**1. A flip counts as fee-driven evidence only if it tracks the cost curve.**
The hurdle falls 0.47 → 0.35 → 0.27 → 0.23. A verdict that improves smoothly
and proportionally across those four points is consistent with fee drag being
the binding constraint. A verdict that jumps erratically, flips at one size and
not a larger one, or improves far more than the ~0.24pp of total hurdle
relief between $5 and $100, is **not** fee-driven — it is noise finding a new
way to express itself, and the single-fold concentration failures already
recorded are exactly what that looks like.

**2. A verdict that stays negative at $100 means the signal has no edge.**
Not "needs more capital". At $100 the hurdle is 0.23% per round trip, within
0.24pp of the $5 case: there is almost no fee relief left to buy. A strategy
still losing there is losing for reasons unrelated to cost, and **that
conclusion is not available for reinterpretation later** as a capital problem.
This clause exists specifically to foreclose that move.

**3. Every pass criterion that applied before still applies.** Majority of
folds positive, pooled positive, no fold contributing >60% of pooled net,
pooled trades ≥ `MIN_POOLED_TRADES` (12), and beating buy-and-hold. A larger
number that fails concentration is the same failure it always was.
Buy-and-hold scales with capital too, and it is re-computed at each size
rather than held at its $10 value.

**4. Any flip is reported with absolute dollar drawdown beside the
percentage.** A 12% drawdown is a different proposition at $5 than at $100, and
the percentage alone hides that. Both figures, every time.

**5. Regime detection cannot flip and will not be reported as if it could.**
Its refutation was that 1 trade in 59 entered a trend-labelled bar. Entry
timing does not depend on position size, so the trend arm is empty at every
size. Re-running it at four sizes would produce four identical empty arms and
dress a non-result as coverage. It is reported as size-invariant, with the
reason.

## Scope

Re-run at **$5 / $10 / $25 / $100**:

1. Parameter sweep (held-out split)
2. Cost-corrected default-parameter runs
3. Walk-forward Phase A
4. Walk-forward Phase B
5. Cross-sectional momentum
6. Regime detection — **size-invariant, stated not re-run** (see rule 5)

## What this does not do

- **It does not change the bot's configured position size.** `RiskConfig`
  defaults stay at $10 and `POSITION_SIZE_SOFT_CEILING_USD` stays where it is.
  The sizes above are research parameters passed to a harness; CLAUDE.md rule 6
  is about the running bot, and it is untouched. The `$25` and `$100` runs must
  set `position_size_override_ack` explicitly, which is the intended friction
  working as designed.
- **It does not authorise trading at any size.** The live gate is unchanged and
  no strategy has cleared it.
- **It does not reopen Stage 6c/6d.** Those stay gated pending an explicit
  instruction naming them.

## The expected outcome, stated in advance

Most likely: everything stays negative, because the recorded failures were
concentration and replication failures rather than fee failures — Phase A's 1h
pooled +0.5815 failed on *concentration*, not on costs, and cross-sectional's
+$13.44 was 94% one fold. Neither is a problem money fixes.

If that is what the numbers say, rule 2 applies and the capital-raise path is
closed on evidence rather than on preference.
