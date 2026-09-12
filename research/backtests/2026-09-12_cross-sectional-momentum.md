# Cross-Sectional Momentum — 5-token Solana universe, $10 total

**Date:** 2026-09-12
**Protocol:** `planning/decisions/2026-09-12-cross-sectional-momentum-protocol.md`,
fixed before the harness was built.
**Universe:** MET, ORE, PUMP, SOL, SPYx — resolved by the record's rule,
not chosen. 127 common daily bars, 2026-04-20 → 2026-09-12.

## Verdict

**All six grid combinations fail. None passes.** Every one fails the
concentration check, and the reason is the same in each case: the result
is a single six-week rally, not an edge.

## The result that proves why the protocol exists

| L | N | fold nets | pooled | trades | fees | verdict |
|---|---|---|---|---|---|---|
| 7 | 1 | −0.709 / +1.516 / **+12.631** | **+13.4381** | 12 | 1.97 | fail: concentration |
| 7 | 2 | −0.900 / +0.005 / +3.811 | +2.9168 | 21 | 2.40 | fail: concentration |
| 14 | 1 | −2.741 / +0.010 / +7.353 | +4.6219 | 8 | 1.42 | fail: concentration, trades |
| 14 | 2 | −1.962 / +0.130 / +4.068 | +2.2358 | 17 | 2.22 | fail: concentration |
| 30 | 1 | −0.076 / +1.310 / +6.480 | +7.7136 | 5 | 0.85 | fail: concentration, trades |
| 30 | 2 | −0.428 / −1.434 / +3.722 | +1.8612 | 13 | 1.85 | fail: majority, concentration |

Look at the top row honestly. **`L=7, N=1` returned +$13.44 on $10 of
capital — more than 8× buy-and-hold SOL's +$1.67 over the same window.**
Quoted alone, that is a spectacular number and it would have been easy to
report as one.

It fails, because **94% of it comes from a single fold** (+12.63 of
+13.44). The concentration check was written into the record before any
of this was run, precisely to catch a number like that. It caught it.

Every other row fails the same way, several worse: the fold-2 share runs
from 84% to over 100% (where a negative earlier fold drags the pool
below the single good fold).

## Why: the folds are the market, not the strategy

Per-token total return by fold, raw price, before any costs:

| Fold | Window | MET | ORE | PUMP | SOL | SPYx |
|---|---|---|---|---|---|---|
| 0 | 04-20 → 06-19 | −6.2% | +30.1% | −23.7% | −18.4% | +6.2% |
| 1 | 06-20 → 07-31 | +10.0% | −21.1% | +46.6% | −0.8% | −0.2% |
| 2 | 08-01 → 09-12 | **+33.1%** | **+23.0%** | **+69.2%** | **+41.6%** | +3.4% |

Fold 2 is a broad rally — **every name in the universe rose**, SOL by
41.6% (71.89 → 101.79, independently consistent with the live SOL price
measured the same day). Fold 0 is broadly down.

The strategy's fold signs track the market's fold signs. So do both
benchmarks:

| | fold 0 | fold 1 | fold 2 | pooled |
|---|---|---|---|---|
| Buy-and-hold SOL | −2.04 | −0.26 | +3.97 | **+1.6705** |
| Equal-weight basket (5) | −1.18 | −0.12 | +2.59 | **+1.2846** |

Same shape, same story. What the grid is measuring is **exposure to a
rally**, dressed as a ranking rule. A strategy that is long something in
a market where everything went up does not need momentum to make money,
and cannot be credited with an edge for having done so.

## A note on the basket benchmark

The equal-weight basket pays **5× the fixed costs on $2 positions** —
$2.50 of fees pooled. At $10 total capital, diversifying across five
names means account rent and per-transaction fees land on positions too
small to absorb them. The basket is the weaker benchmark here for a
reason that has nothing to do with momentum: it is the capital
constraint, visible directly.

## Interpretation ceiling

Fixed before the run and unchanged by it. Had any combination passed, the
correct reading would have been:

> **"Not refuted, on a single regime, on a five-token universe. Cannot
> generalize to cross-sectional momentum as a class."**

Nothing passed, so that ceiling is not even in play. But it is recorded
here so that no future re-read of this file upgrades the language.

Also unchanged: positions are **fixed-notional** ($10/N each, P&L not
reinvested), so returns here do not compound. That keeps exposure at $10
and rule 6 intact, and it means the pooled figures are sums of
independent round trips rather than a growth curve.

## What was deliberately not done

Per the record: the grid was not widened, the universe was not changed,
RAY was not re-admitted, the rebalance cadence was not adjusted, and no
combination was selected after seeing results. **All six are reported** —
which is what makes selection impossible rather than merely discouraged.
Capital was not raised in response to the cost drag.

## Where this leaves the momentum hypothesis

This is the fifth converging negative, and the first one testing a
genuinely different *form* of momentum rather than different parameters
of the same one. Single-pair momentum failed four ways; cross-sectional
momentum, on the best universe this data supports, fails on the first
honest check.

The limitation stated in the decision record still applies and is now
load-bearing: **~6 months containing one broad rally is plausibly one
regime**, and a five-name universe is thin for a cross-sectional
strategy. A negative result on one regime does not disprove
cross-sectional momentum as a class — it says this data cannot support
the claim, which is a different and weaker statement than "the effect is
absent."

What it does rule out is proceeding on the strength of a +$13.44 number.
