# Where could an edge even live? — 2026-09-14

`trade_power.py` answered *how big* an edge must be for us to detect it at our
size. This answers the question that follows: **at which holding periods is an
edge that large physically available**, given how much price actually moves.

Strategy-agnostic throughout. It measures realised return distributions on real
cached bars and derives what any directional strategy would have to achieve.

## The headline

**Every horizon that survives both constraints requires 73.8%–94.8% direction
accuracy.**

| Horizon | Trades/30d | E&#124;move&#124; | Floor | Accuracy needed |
|---|---|---|---|---|
| 15m ×1 | 1453 | 0.272% | 0.154% | 78.3% |
| 15m ×2 | 727 | 0.356% | 0.176% | 74.7% |
| **15m ×4** | **373** | **0.449%** | **0.214%** | **73.8%** ← least demanding |
| 15m ×8 | 183 | 0.591% | 0.289% | 74.4% |
| 1h ×1 | 372 | 0.430% | 0.218% | 75.4% |
| 1h ×4 | 93 | 0.791% | 0.467% | 79.5% |
| 4h ×1 | 87 | 0.825% | 0.482% | 79.2% |
| 4h ×4 | 22 | 1.712% | 1.535% | 94.8% |
| 1d ×1 | 14 | 2.140% | 2.243% | **DEAD** — unreachable at 100% |
| 1d ×2+ | <12 | — | — | too few trades |

Merely covering costs needs 51–73%. Producing an edge a 30-day window can
*confirm* needs 74%+ everywhere.

Published directional accuracy on liquid crypto rarely clears the mid-50s. A
horizon demanding 73.8% is a refutation in all but name.

## Why the middle of the range is the best of a bad set

Two forces pull against each other, and the table is where they meet:

- **Longer holds carry bigger moves** — easier to clear the $0.0127 fixed cost.
- **Longer holds yield fewer trades** — harder to distinguish edge from luck.

Short horizons drown in costs; long ones starve for sample. The least demanding
point is ~1 hour of holding (15m ×4), and it still asks for 73.8%.

## Volatility does not rescue this

The obvious next move is "trade something wilder". Measured across every cached
pool at a one-day hold — a **10.9× range** in daily volatility:

| Pool | E&#124;move&#124; | Stdev | Noise ratio | Accuracy needed |
|---|---|---|---|---|
| 6truu3rZ | 0.57% | 0.78% | 1.36 | 108.5% |
| 8sLbNZoA | 2.14% | 2.87% | 1.34 | 102.4% |
| 58oQChx4 | 2.17% | 2.90% | 1.33 | 103.0% |
| BnztueWc | 4.30% | 5.92% | 1.38 | 101.9% |
| 2uF4Xh61 | 4.37% | 5.92% | 1.35 | 100.0% |
| C7hF6MvQ | 6.22% | 9.65% | **1.55** | 106.9% |

**An 11× change in volatility moves the requirement by about 8 points, and not
monotonically — the most volatile asset needs *more* accuracy than one a third
as volatile.**

The reason is in the noise-ratio column, which is nearly invariant at 1.33–1.55:
volatility raises the edge available and the noise to be overcome *together*.
Only the fixed-cost term is relieved, and it is already small beside the noise.
The most volatile pool is worse because its ratio is worse — fatter tails.

## What this explains

Six protocol-bound tests failed on this project: momentum (six ways),
cross-sectional momentum, regime detection. Each was investigated separately
and each failure was recorded as its own result.

**They share one structural cause.** Every one was a directional-prediction
strategy on liquid Solana pairs at 15m–4h, which this table says would have
needed ~74–80% accuracy to produce a detectable edge. The tests were run
correctly; the question was not answerable at that size and horizon.

That is a cheaper explanation than six independent ones, and it was available
in an afternoon of arithmetic rather than weeks of backtesting.

## What it does NOT say

- **It does not say trading is impossible here.** It says *directional
  prediction of price on liquid pairs* cannot carry a detectable edge at $5–$10
  over 15m–1d. An edge whose payoff is not a draw from that return distribution
  — mechanical, event-driven, or structural — is untouched by this analysis.
- **It rules horizons out; it never rules one in.** A surviving horizon means an
  edge there is not impossible, not that one exists.
- **It assumes a symmetric, long-only directional caller.** The oracle column is
  a looser bound (a selective trader that takes only winners). Both are reported.

## Two errors caught in this file's own drafts

Recorded because both flattered the result, and both were caught by re-deriving
rather than re-reading:

1. **One detection floor applied to every horizon.** Ignored that a longer hold
   yields fewer trades. It made `1d ×8` look like it needed 53.6% accuracy; the
   honest figure is that it yields under four round trips in a month and can
   confirm nothing.
2. **Oracle gross averaged over windows while every window counted as a trade.**
   The oracle skips losers, so its gross and its sample were on different bases
   — understating the trade and overstating the count simultaneously.

Both are now pinned by tests that fail if the old behaviour returns.

## Where this points

If directional prediction is out at our size, the search should move to edges
whose payoff does not come from the return distribution: mechanical or
event-driven situations where the profit is structural rather than predictive.
Whether such an edge is reachable with our data access is a separate question
this analysis does not answer — and given the copy-trading and pump.fun
feasibility findings, it should be asked before another window is spent.
