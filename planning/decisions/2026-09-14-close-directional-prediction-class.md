# Decision: directional prediction on liquid Solana pairs is CLOSED as a class

**Date:** 2026-09-14
**Status:** Class closure. Supersedes the standing constraint recorded in
`2026-09-14-directional-prediction-is-out.md` by replacing a rule with the
reason the rule exists.
**Derivation:** `research/backtests/2026-09-14_edge-budget.md` (PR #11)

## The closure

> **No strategy whose payoff is a draw from the price return distribution of a
> liquid Solana pair, traded at $5–$10 over 15m–1d horizons, will be tested
> individually again. The class is closed.**

## Why this is a class closure and not a tally

It would be easy, and wrong, to summarise the last two weeks as *"we tried five
strategies and they all failed, so let's be careful about the sixth."* That
framing invites a sixth, because each failure looks like it might have been the
strategy's fault.

The actual finding is stronger and has nothing to do with how many were tried:

**Every horizon capable of both carrying the edge and producing enough trades
to prove it requires 73.8%–94.8% direction accuracy.** The least demanding
point — about an hour of holding — asks for **73.8%**. Merely covering the
$0.0127 fixed cost needs 51–73%.

Published directional accuracy on liquid crypto rarely clears the mid-50s.
The requirement is not near the achievable range; it is roughly twenty points
outside it.

That is a statement about **the instrument**, not about any strategy. It holds
for a strategy nobody has written yet. So the correct response is not to be
more careful about the next one — it is to stop generating them.

## The two constraints that produce the bound

They pull in opposite directions, which is why no horizon escapes:

- **Short holds drown in fixed costs.** $0.0127 per round trip does not scale
  down. At 15m the average absolute move is 0.272%; the cost alone eats a
  meaningful share of it.
- **Long holds starve for sample.** A 30-day window at a one-day hold yields
  ~14 round trips — below `MIN_POOLED_TRADES`. `1d ×1` is marked **DEAD**: its
  detection floor (2.243%) exceeds its own average move (2.140%), so it is
  unreachable even at 100% accuracy.

Between those, the best available point still asks for 73.8%.

## Volatility does not relieve it

The obvious escape — trade something wilder — was measured, not assumed.
Across a **10.9× range** of daily volatility, the requirement moves about
**eight points and not monotonically**: the most volatile pool needs *more*
accuracy than one a third as volatile.

The reason is a near-invariant: the noise ratio (stdev ÷ E|move|) sits at
**1.33–1.55** across every pool measured. Volatility raises the edge available
and the noise that must be overcome together. Only the fixed-cost term is
relieved, and it is already small beside the noise. The wildest pool is worse
because its tails are fatter.

## What this retires

These verdicts stand on their own evidence and are not replaced — they are now
*explained*:

| Hypothesis | Its own verdict | Now also explained by |
|---|---|---|
| EMA/RSI momentum | Closed, six converging negatives | Directional at 15m–4h |
| Cross-sectional momentum | Failed the concentration check | Directional at 1d |
| Regime detection | Refuted at the mechanism | Directional, conditioned |
| Capital-range increase | Closed — costs were never the constraint | Same bound, read from the other end |

Four separate investigations, one structural cause. That cause was computable
in an afternoon and was available before any of them ran.

## The process change this forces

Every one of those tests was executed correctly. The protocol was followed:
pre-registration, walk-forward folds, concentration checks, held-out splits.
**The failure was upstream of the protocol** — nobody asked whether the
measurement was capable of returning a trustworthy answer before spending a
window on it.

That check is now mandatory and codified: `.claude/skills/edge-viability-check`.
An afternoon of arithmetic comes before weeks of backtesting, from here.

## What this does NOT close

- **Structural edges** — where profit comes from a mechanical situation rather
  than from being right about direction. Whether anything remains open there is
  a separate question, audited in
  `.claude/skills/structural-edge-inventory` and summarised in
  `planning/architecture/2026-09-14-structural-edge-inventory.md`. **Do not
  assume that reframe opens a frontier.**
- **The same question at a materially different scale.** The bound is a
  function of position size, fixed cost and the return distribution. Change one
  materially and `research/edge_budget.py` recomputes it. Nothing here is a
  claim about trading in general.
- **The execution stack.** Complete, hardened, and correct. It has no strategy
  to run, which is a different problem from a broken machine.

## Reopening condition

Stated so that reopening is possible but deliberate: this closes only while the
bound holds. It is void if **any** of these changes materially, and
`edge_budget.py` is re-run to show it:

1. Fixed cost per round trip falls far enough to move the break-even row.
2. Position size rises far enough to shrink the fixed-cost term's share.
3. A pair is traded whose noise ratio is materially below 1.33.

A new idea within the class is **not** a reopening condition. Neither is
conviction about one.
