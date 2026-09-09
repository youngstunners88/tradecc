# Parameter Sweep and Held-Out Validation — momentum, SOL/USDC

**Date:** 2026-09-09
**Protocol:** `planning/decisions/2026-09-09-tuning-holdout-split.md`,
written and committed before any parameter was changed.

## Verdict

**No net edge at $10 on held-out data.** Per the stopping rule fixed in
advance, the search stops here.

- **1h** failed outright: tuning +$0.86 → held-out **−$0.66**.
- **4h** was nominally positive at +$0.47, but on **3 trades**. That is
  not evidence of an edge; it is one winning trade and two losers.
- **1d** produced no eligible configuration (fewer than 10 trades on the
  tuning range), exactly as the decision record anticipated.

## Results

Grid: 144 combinations per interval (`fast_ema` × `slow_ema` ×
`rsi_period` × `rsi_overbought`), position size $10, all risk settings at
defaults.

### Tuning range (selection happened here)

| Interval | Eligible configs (≥10 trades) | Positive net expectancy | Winner | Trades | Net |
|---|---|---|---|---|---|
| 1h | 96 / 144 | **21 / 96 (22%)** | fast 20, slow 21, rsi 21, ob 70 | 11 | +$0.86 |
| 4h | 91 / 144 | **11 / 91 (12%)** | fast 12, slow 34, rsi 21, ob 80 | 10 | +$0.69 |
| 1d | 0 / 144 | — | none | — | — |

**78–88% of the parameter space lost money on the range it was tuned on.**
Selecting the maximum of a distribution that is mostly negative is
selection bias with extra steps, and the held-out results below are what
that looks like when it is checked.

The 1h winner is also a tell: `fast_ema=20` against `slow_ema=21` is not
a momentum crossover in any meaningful sense — the two averages track
each other almost exactly, so it fires on noise. That is the shape of an
overfit parameter set.

### Held-out range (one configuration per interval, one shot)

| Interval | Range | Trades | Gross | Fees | **Net** | Expectancy | Win rate |
|---|---|---|---|---|---|---|---|
| 1h | 2026-08-28 → 09-09 | 3 | −$0.24 | $0.41 | **−$0.66** | −$0.219 | 66.7% |
| 4h | 2026-07-21 → 09-09 | 3 | +$0.88 | $0.41 | **+$0.47** | +$0.156 | 33.3% |

Three trades per interval. Neither number supports a conclusion, and the
one that is positive is positive on a 33% win rate — a single trade
carried it.

## Correction: what the cost actually is

Earlier write-ups in this repo (including the README) said fixed costs
were roughly 1.4× the gross edge and dominated at $10. **That framing was
wrong, and the sweep exposed it.** The breakdown at $10, SOL at $200:

| Component | Per transaction | Scales with size? |
|---|---|---|
| Base fee (5,000 lamports) | $0.001 | No |
| Priority fee (as configured) | $0.00000004 | No |
| ATA rent | $0.4079, **once per mint** | No |
| Assumed slippage | 0.3% each way | **Yes** |

The recurring per-round-trip fee at $10 is **$0.002 — about 0.02%**,
which is negligible. The $0.41 that appears in every "fees" column is
almost entirely the **one-time** associated-token-account rent, charged
on the first trade in a mint and amortised across however many trades
follow. With only 3 held-out trades it looks enormous; over 300 trades it
would be a rounding error. It is also a **rent-exempt deposit that is
refundable when the account is closed**, so calling it a cost at all
overstates it.

The genuinely recurring drag is **slippage: 0.6% per round trip, roughly
30× the recurring fees**, and it is embedded in the gross P&L rather than
the fees column. Slippage is *proportional* to position size.

### What this means for "test a larger position size"

Larger positions amortise the one-time rent and shrink the fixed-fee
share to nothing. They do **not** touch the slippage drag, which is the
dominant recurring cost and stays at 0.6% per round trip at any size.

So raising size would improve these numbers, but it does not create an
edge — it removes an amortisation artefact and leaves the real hurdle
untouched. The strategy needs an average gross move **greater than ~0.6%
per round trip** to be viable, and nothing in this sweep suggests it has
one.

## Two caveats about the cost model itself

1. **Priority fees are almost certainly understated.** The config treats
   `priority_fee_microlamports` as a flat total (200,000 µlamports = 0.2
   lamports). Real priority fees are quoted *per compute unit*; a swap at
   ~200k CU would be several orders of magnitude more. This should be
   re-modelled before any live sizing decision.
2. **Jito tips are not modelled at all**, and MEV-protected routing on
   Solana typically involves one. That is a further per-transaction cost
   currently counted as zero.

Both errors run in the same direction: **real costs are higher than
modelled**, which makes the held-out results optimistic rather than
pessimistic.

## What was not done, deliberately

Per the stopping rule in the decision record: the grid was not widened,
no indicators were added, no alternative date range was searched, and the
held-out slice was scored exactly once per interval. Each of those would
have been a way of fitting the validation data by hand.

## Recommended next step

Not further tuning, and not Stage 6. The decision the evidence actually
supports is a **cost-model correction first** (priority fees, Jito tips),
because the current model understates the hurdle the strategy must clear.
Any position-sizing decision rests on numbers that are currently wrong in
the flattering direction, and sizing up is the user's call under
CLAUDE.md rule 6 regardless.
