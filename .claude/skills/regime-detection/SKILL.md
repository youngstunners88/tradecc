---
name: regime-detection
description: Classify market regime (trend / chop / volatility) and condition strategy behaviour on it — the most defensible explanation for why the momentum sweep failed on held-out data. Use when adding regime logic, deciding whether to trade at all in a given window, or extending the parameter search. Carries the anti-overfit protocol, because regime conditioning multiplies the search space and is the fastest way to manufacture a fake edge.
---

# Regime detection

## Why this exists

The held-out sweep found **no net edge at $10**, and the shape of the
failure is informative. 78–88% of the parameter space lost money *on the
range it was tuned on*. The 1h winner was `fast_ema=20` against
`slow_ema=21` — two averages that track each other almost exactly, so it
fired on noise.

That is what an EMA crossover does in a chopping market: it crosses
constantly, pays the full cost stack each time, and gives back more than
it makes. Momentum strategies have a known mechanism — they earn in
trends and bleed in ranges. The v0.1 bot **traded identically in both.**

So regime conditioning is not a new indicator bolted on in hope. It is
the specific hypothesis that matches the observed failure: *the
strategy's losses are concentrated in a market state that is
identifiable in advance.*

That hypothesis is testable, and it might be false. Treat it as a
hypothesis until the held-out data says otherwise.

## The honest framing of "where will the market move"

This layer does not forecast price. It classifies **which of a small
number of states the market is currently in**, and each state carries a
different action — including, most often, *do not trade*.

The distinction matters because a price forecast is unfalsifiable in
practice at this sample size, while a regime label makes a concrete,
checkable claim: "in windows I labelled chop, the strategy's expectancy
was negative." You can verify that on data you already have.

## The three states worth separating

Start with the smallest set that carries different actions. More states
means more parameters means more overfitting.

| Regime | Rough character | Momentum action |
|---|---|---|
| **Trend** | Directional, expanding range | Trade — this is the only state the strategy has a mechanism for |
| **Chop** | Mean-reverting, contained range | **Stand down.** Crossovers here are noise paying full costs |
| **High volatility** | Wide, erratic, gappy | Stand down, or size down hard — stops get skipped, slippage widens |

**"Stand down" is a real, valuable output.** At $10 sizes with ~0.6%
round-trip slippage, not trading is frequently the highest-expectancy
action available. A regime filter that only ever removes trades can
improve net P&L without improving the signal at all — the same
mechanical logic as the liquidity gate in `market-intelligence`.

## Candidate classifiers

All computed in `Decimal` from closed candles, in the style of
`strategy/indicators.py` — hand-rolled, aligned to input length, `None`
during warmup. Do not reach for pandas in the signal path; the reasons in
the README still apply.

- **ADX** — the standard trend-strength measure. Below ~20 conventionally
  reads as rangebound. Its warmup is long, which costs decision bars.
- **Realised volatility ratio** — short-window stdev of returns over a
  long-window stdev. Cheap, no new concepts, separates expansion from
  contraction.
- **Efficiency ratio (Kaufman)** — net displacement ÷ sum of absolute
  moves over the same window. Near 1 is clean trend, near 0 is chop.
  This is the most direct measurement of the thing that actually hurts a
  crossover strategy, and it is trivial to compute exactly.

**Start with the efficiency ratio alone.** One classifier, one threshold,
one new parameter. The temptation is to add all three and vote; resist
it until one has earned its place on held-out data.

## Anti-overfit protocol — read before touching parameters

Regime conditioning multiplies the search space: every regime threshold
is a new dimension, and each regime can carry its own strategy
parameters. The 144-combination sweep that already failed becomes
thousands. **The probability of finding a spurious winner rises with
it,** and the existing evidence shows this codebase's search is already
operating in a mostly-negative distribution where taking the maximum is
selection bias.

Therefore, binding rules:

1. **Write a decision record before any parameter is tried**, following
   `planning/decisions/2026-09-09-tuning-holdout-split.md`. Fix the
   split, the grid, the selection rule, the minimum trade count, and the
   stopping rule in advance.
2. **The held-out slice is already spent.** It was scored on 2026-09-09.
   Re-using it to validate a regime filter is not held-out validation —
   it is a second look at data whose answer is now known. Either source
   genuinely new history, or use walk-forward with multiple
   non-overlapping folds and report every fold, not the best one.
3. **Regime thresholds are parameters and count against the budget.**
   A "filter" with a tuned cutoff is not free; it is the same search in
   different clothing.
4. **Test the mechanism, not just the P&L.** Before optimising anything,
   check the claim directly: label the existing history by regime and
   compare expectancy in trend-labelled windows against chop-labelled
   windows, at the **default** parameters. If the gap is not there at
   defaults, regime conditioning is not the explanation, and tuning until
   it appears is fitting noise.
5. **Report trade counts beside every result.** The prior sweep produced
   "+$0.47 on 3 trades." A filter that stands down most of the time will
   produce very few trades — and few trades cannot distinguish skill from
   luck, whichever direction they point.

Step 4 is the cheapest and most informative thing in this file. Do it
first, and be prepared for it to say no.

## Where regime output goes

A regime label is an **input to the deterministic strategy**, resolved
before the signal, from closed candles only. Same constraints as any
other indicator:

- **No look-ahead.** The label at bar N uses `candles[:N+1]`. A regime
  computed from the full series and applied retroactively will look
  spectacular and mean nothing.
- **It is a filter, not a signal.** A regime label may suppress a trade
  the strategy proposed. It may not originate one. This preserves the
  existing signal path and keeps the change auditable.
- **It runs in backtest, paper, and live identically**, like everything
  else — otherwise the paper run is evidence about a different system.

## What would make this worth keeping

Set the bar before running, not after:

- Expectancy in trend-labelled windows measurably above chop-labelled
  windows **at default parameters** (the step-4 check).
- Net-of-cost expectancy positive across **every** walk-forward fold, not
  averaged across them.
- Enough trades per fold to be worth reading — the sweep's `MIN_TRADES`
  of 10 was already generous for the conclusions it supported.

If it does not clear that, the finding is "regime conditioning did not
rescue this strategy", which is a real result. Write it up in
`research/backtests/` and stop, exactly as the sweep did.
