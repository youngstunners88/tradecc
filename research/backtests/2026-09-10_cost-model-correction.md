# Cost Model Correction — re-running Stage 5 at 1h and 15m

**Date:** 2026-09-10
**Scope:** four corrections to the cost model, applied to the same
candles and the same default parameters as the Stage 5 runs. No strategy
or parameter changed.

## Verdict

**The picture changes, and the net direction is favourable — but almost
all of the improvement comes from a number that is still assumed, not
from one that is now measured.**

- **15m stays clearly unprofitable** at every plausible assumption. That
  conclusion is robust and unchanged.
- **1h moves from −$0.12 to +$0.58**, which looks like a sign flip. It
  is not safe to read it as one: at the *old* slippage assumption the
  same corrected model returns −$0.02. The entire result sits inside the
  band of one judgement call.

## What was corrected

| # | Correction | Was | Now | Direction on P&L |
|---|---|---|---|---|
| 1 | SOL price | hardcoded $200 | each bar's own close | **up** (costs fell) |
| 2 | Priority fee | flat total (0.2 lamports) | per compute unit (40,000 lamports) | **down** |
| 3 | Jito tip | not modelled | 17,392 lamports (75th pct measured) | **down** |
| 4 | Slippage | 0.30%/side assumed | 0.01%/side measured impact + 0.10%/side assumed execution | **up** |

Corrections 1 and 4 pull one way, 2 and 3 the other. That is why a single
before/after number would have been misleading, and why the runs below
apply them cumulatively.

### On correction 1

The config constant said $200. Mean SOL over the 1h window was **$87.53**
and over the 15m window **$103.15**. Because the backtest pair *is*
SOL/USDC, the bar's close is the SOL price — so this is now exact and
offline rather than a constant that drifts.

### On correction 4, which does most of the work

Jupiter's quote reports `priceImpactPct` for a real size on a real route.
Measured 2026-09-10 on SOL/USDC:

| Size | Measured impact |
|---|---|
| $5 | 0.0000% |
| $10 | 0.0044% |
| $50 | 0.0012% |
| $200 | 0.0000% |

The pool holds ~$834M. A $10 trade does not move it. The earlier
write-up's claim that **"slippage at ~0.6% per round trip is the dominant
recurring cost, roughly 30× the recurring fees"** was wrong by roughly
two orders of magnitude for this pair at this size.

The 0.5% gap to `otherAmountThreshold` is **not** a cost. It is the
slippage tolerance requested — the worst case the route guarantees
against, not what a fill is expected to pay. Conflating the two is what
produced the 0.3%/side figure.

## Results

Cumulative — each row adds one correction to the row above, so the
marginal effect of any single change is the delta column. All rows price
SOL-denominated costs per bar.

### 1h — 1000 candles, 2026-07-29 → 2026-09-09

| Stage | Trades | Gross | Fees | **Net** | Δ |
|---|---|---|---|---|---|
| *(recorded 2026-09-09, $200 SOL)* | 15 | +0.32 | 0.44 | **−0.12** | — |
| 0. per-bar SOL price only | 15 | +0.3195 | 0.1632 | **+0.1564** | +0.28 |
| 1. + priority fee per CU | 15 | +0.3195 | 0.2657 | **+0.0538** | −0.10 |
| 2. + Jito tip | 15 | +0.3195 | 0.3103 | **+0.0092** | −0.04 |
| 3. + measured impact | 15 | +0.8918 | 0.3103 | **+0.5815** | **+0.57** |

### 15m — 1000 candles, 2026-08-30 → 2026-09-09

| Stage | Trades | Gross | Fees | **Net** | Δ |
|---|---|---|---|---|---|
| *(recorded 2026-09-09, $200 SOL)* | 23 | −2.14 | — | **−2.59** | — |
| 0. per-bar SOL price only | 23 | −2.1350 | 0.2387 | **−2.3738** | +0.22 |
| 1. + priority fee per CU | 23 | −2.1350 | 0.4285 | **−2.5635** | −0.19 |
| 2. + Jito tip | 23 | −2.1350 | 0.5110 | **−2.6460** | −0.08 |
| 3. + measured impact | 23 | −1.2675 | 0.5110 | **−1.7785** | **+0.87** |

Trade count is identical at every stage: the corrections change what
trades cost, not which trades happen. Gross changes only at stage 3
because fill prices move, which shifts where stops and take-profits land.

## The caveat that matters most

The slippage correction splits into a measured part and an assumed part,
and **the assumed part is ~23× larger than the measured one**:

- `price_impact_pct = 0.01%` — measured (0.0044% observed, rounded up).
- `execution_slippage_pct = 0.10%` — **assumed**. Quote-to-fill drift.
  No historical measurement can supply it, and a momentum strategy buys
  into rising prices, so it is adverse by construction.

Sensitivity of net P&L to that assumption, impact held at 0.01%:

| Assumed execution slippage/side | 1h net | 15m net |
|---|---|---|
| 0.00% | +0.8836 | −1.3206 |
| 0.05% | +0.7325 | −1.5497 |
| **0.10% (chosen)** | **+0.5815** | **−1.7785** |
| 0.15% | +0.4307 | −2.0071 |
| 0.20% | +0.2800 | −2.2355 |
| 0.30% (the old assumption) | −0.0209 | −2.6916 |

**1h crosses zero at roughly 0.29%/side.** The positive result therefore
depends entirely on believing execution slippage is well under the old
assumption. The measurement supports that for *price impact*; it says
nothing about quote-to-fill drift.

**15m is negative across the whole band**, so no choice of this parameter
rescues it.

## What this does and does not license

**Does:** the cost model is now materially more accurate. Two errors that
ran in opposite directions are both fixed, and the largest single input
is measured rather than invented.

**Does not:**

1. **This is not evidence the strategy works.** It is the same 1000
   candles at default parameters, on the range the earlier sweep already
   examined. It is not a held-out result.
2. **The 1h number is not a discovered edge.** +$0.58 over 15 trades is
   +$0.039 expectancy per trade, inside the sensitivity band of one
   assumption, on a sample too small to distinguish from noise.
3. **The held-out slice from 2026-09-09 is spent.** It has been scored;
   re-scoring it against a changed cost model is not out-of-sample
   validation. Any re-run of the parameter exploration needs either new
   history or walk-forward folds with every fold reported.

## Recommended next step

Measure the assumed component instead of arguing about it. Paper mode
already quotes real Jupiter prices; recording quoted price against
simulated fill price over a paper run turns `execution_slippage_pct`
from a judgement call into a measurement, and it is the only input still
capable of flipping the 1h sign on its own.
