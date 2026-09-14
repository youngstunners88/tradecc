# Decision: the minimum edge worth hunting, derived from our position size

**Date:** 2026-09-14
**Status:** Adopted as a filter on strategy search. Changes no risk default, no
gate condition, and no position size.

## The question this answers

The plan is: trade small, watch real results, scale what works. The reasonable
worry about that plan is "small trades teach you nothing". This checks whether
that worry is true, using measured numbers rather than intuition.

It is **half** true, and the half that is false is the more useful half.

## Two measured inputs

| Input | Value | Source |
|---|---|---|
| Fixed cost per round trip | **$0.0127** | `research/calibrate_costs.py`, recurring only — refundable ATA rent is a deposit, not a fee |
| Per-trade net return stdev | **0.951% of position size** | 23 recorded round trips, SOL/USDC 15m |
| Observed trade frequency | **2.35 round trips/day** | same window, 940 bars |

The standard deviation is a property of the pair and the holding period, not of
any strategy's edge, so it transfers to whatever we test next on the same bars.

## Finding 1 — small size is *fine* for a strong edge, and fast

This is the part that supports trading small, and it was not obvious:

| True gross edge | Round trips to confirm at $10 | Calendar time |
|---|---|---|
| 2.0% | 2 | under a day |
| **1.0%** | **9** | **4 days** |
| 0.5% | 51 | 22 days |
| 0.2% | 1,332 | 19 months |

A genuinely strong edge announces itself in **about a dozen round trips**, and
at $10 a size that costs roughly **$0.12 in fees** to find out. The instinct
that we can learn cheaply at small size is correct — *provided the edge is
large*.

## Finding 2 — small size cannot detect a weak edge at all

Fixed costs do not scale, so the percentage hurdle rises as size falls:

| Size | Break-even gross edge |
|---|---|
| $5 | **0.254%** |
| $10 | 0.127% |
| $25 | 0.051% |
| $100 | 0.013% |

At $5, a 0.2% gross edge is **not merely hard to detect — it is negative after
costs**. The table above reads "never", and that is literal: no sample size,
no patience, and no amount of real-money experience recovers it. This is the
same arithmetic that closed the capital-raise path in
`2026-09-13-capital-range-sensitivity.md`, read from the other end.

## Finding 3 — the 30-day gate window has its own floor

At 2.35 round trips/day, 30 days is ~70 round trips. That window can confirm:

| Size | Smallest edge a 30-day run could confirm |
|---|---|
| $5 | 0.572% |
| $10 | 0.445% |
| $25 | 0.369% |
| $100 | 0.331% |

So the validation gate, as configured, is an instrument that can only see edges
of roughly **half a percent per round trip or larger**. Anything subtler passes
or fails it by luck.

## The decision

> **A hypothesis is not worth testing unless its plausible edge clears the
> detection floor for the size we actually trade — about 0.5% gross per round
> trip, and never below the break-even hurdle for that size.**

This becomes a pre-registration question, alongside the existing ones: *what
edge does this hypothesis claim, and is that edge detectable in the window we
will run?* A hypothesis that cannot answer it is not ready to test.

`research/trade_power.py` computes the floor for any size, cost and frequency.

## Why this matters more than it looks

**Momentum was tested six ways at an edge far below this floor.** Its measured
per-trade expectancy was −$0.0079 and later −$0.0773 on $10 — around −0.08% to
−0.8% per round trip. Even had it been mildly positive, the window could not
have proven it. Six careful, protocol-bound tests were spent on a question the
instrument could not resolve.

That is the process failure this record exists to prevent, and it is not a
failure of rigour — every one of those tests was run correctly. It is a failure
to check, in advance, whether the measurement was capable of the answer.

## What this does NOT change

- **No risk default moves.** Position size stays at $5–$10 per CLAUDE.md rule 6.
- **No gate condition is relaxed.** 30 days, positive net expectancy,
  `MIN_POOLED_TRADES`, the 8% drawdown threshold and human approval all stand.
- **It is not a claim that a ≥0.5% edge exists.** It is a statement about what
  our instrument can see. Finding such an edge is a separate, unsolved problem.
- **It does not authorise live trading.** Stage 6c/6d — signing and sending —
  remains stood down pending an explicit instruction naming it.

## The honest consequence

Small-budget trading is a good way to find a **big** edge cheaply, and a
useless way to find a **small** one. So the search should be pointed at
hypotheses with large, structural, short-lived edges rather than at statistical
tendencies in price series — the latter are exactly the class whose edges live
below our floor.
