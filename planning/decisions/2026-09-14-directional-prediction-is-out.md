# Decision: stop looking for an edge in directional price prediction

**Date:** 2026-09-14
**Status:** Adopted as a search filter. Changes no code, no risk default, no
gate condition. Closes a *class* of hypothesis, not a specific one.
**Evidence:** `research/backtests/2026-09-14_edge-budget.md`

## The decision

> **Do not open another hypothesis whose payoff is a draw from the price return
> distribution of a liquid Solana pair at 15m–1d, at $5–$10 per position.**

Not because such hypotheses are uninteresting, and not because the previous
ones were tested badly. Because the arithmetic says the measurement cannot come
back trustworthy either way.

## What forced it

Every horizon that can both carry the edge and produce enough trades to prove
it requires **73.8%–94.8% direction accuracy**. The least demanding point is
about an hour of holding, and it asks for **73.8%**.

Covering costs alone needs 51–73%. Clearing the floor a 30-day window can
*confirm* needs 74%+ everywhere. Directional accuracy on liquid crypto rarely
clears the mid-50s in published work.

Two forces set that: short holds drown in the $0.0127 fixed cost; long holds
starve for sample. There is no horizon where both are comfortable — only a
least-bad middle.

**Volatility does not rescue it.** Across a 10.9× range of daily volatility the
requirement moves ~8 points and not monotonically; the most volatile pool needs
*more* accuracy than one a third as volatile. The noise ratio (stdev ÷ E|move|)
is nearly invariant at 1.33–1.55 — volatility raises the available edge and the
noise together.

## Why this is worth writing down rather than just knowing

**It explains six failures with one cause.** Momentum (six ways),
cross-sectional momentum, and regime detection were each investigated
separately and recorded as independent results. They were all directional
prediction on liquid pairs at 15m–4h. Every one was asking a question the
instrument could not answer.

That is a cheaper explanation than six, and it was available in an afternoon of
arithmetic rather than weeks of backtesting. The process failure was not
rigour — each test was run correctly — but never checking whether the
measurement was *capable* of the answer before spending the window on it.

This record, with `2026-09-14-minimum-detectable-edge.md`, makes that check
mandatory rather than optional.

## What remains open

The analysis bounds strategies whose profit is a draw from the return
distribution. It says nothing about edges that are **structural rather than
predictive** — where the payoff comes from a mechanical situation rather than
from being right about where price goes next.

That is the only remaining direction this project has not closed. It is also
the one where the data-access findings already recorded
(`copy-trading-wallet-universe`, `pumpfun-graduation-feasibility`) bite hardest:
both structural candidates examined so far were blocked on data infrastructure
rather than on economics.

**So the honest next question is not "which strategy?" but "which structural
edge is reachable with the data access we actually have?"** That should be
answered before another test window is committed.

## What this does NOT do

- **It does not close the project.** The execution stack is complete and
  hardened; it has no strategy to run, which is a different problem from a
  broken machine.
- **It does not forbid revisiting** if the inputs change. A materially lower
  fixed cost, a materially larger position size, or a genuinely different
  return distribution would each move the table, and the tool recomputes it.
- **It does not apply to the hypotheses already closed on their own evidence.**
  Those verdicts stand on their own; this explains them, it does not replace
  them.
- **It is not a claim that no edge exists.** It is a claim about what our
  instrument can see, at our size, on these pairs, over these horizons.
