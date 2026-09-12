---
name: regime-detection
description: Classify market regime (trend / chop / volatility) and condition strategy behaviour on it. REFUTED on the v0.1 momentum strategy — the mechanism check found an empty trend arm, so this skill is dormant for that strategy and live only for a future strategy whose entries actually land in trend-labelled bars. Read it for the mechanism-check protocol and the anti-overfit rules, which are general and still binding. Carries the anti-overfit protocol, because regime conditioning multiplies the search space and is the fastest way to manufacture a fake edge.
---

# Regime detection

## Status: hypothesis refuted on current data (2026-09-12)

**Do not treat this skill as live work on the v0.1 momentum strategy.** Its
own step-4 mechanism check was run before any parameter was tried, and it
failed at the premise:

> One trade out of 59 was entered in a trend-labelled bar. 1h and 4h had an
> **empty trend arm** (n=0); 15m had n=1.

Measurement, harness and full numbers:
`research/backtests/2026-09-12_regime-detection-pre-registration.md` and
`research/regime_check.py`.

**Reopening condition.** This skill becomes live again only when a strategy
exists whose entries actually land in trend-labelled bars — that is a property
of the *strategy*, not of the regime layer. Re-run the mechanism check against
that strategy first. Until then, the sections below are kept for the
classifier notes, the anti-overfit protocol, and the look-ahead constraints,
all of which remain correct and apply to any future conditioning work.

## Why this exists

It was written on the hypothesis that the momentum failure was a
regime-blindness failure: that the strategy earns in trends and bleeds in
ranges, traded identically in both, and could be rescued by standing down in
chop.

**That hypothesis has been measured and is wrong**, in a specific and more
informative way than "it did not help."

Labelling history by Kaufman efficiency ratio (window 20, threshold 0.4 named
before running) at default parameters:

| Interval | trades | TREND arm | CHOP arm |
|---|---|---|---|
| 1h | 15 | **n=0** | n=15, exp +0.0388 |
| 4h | 21 | **n=0** | n=21, exp −0.0262 |
| 15m | 23 | n=1 | n=22, exp −0.0756 |

The classifier is not the problem — labels flip 34–78 times per series, so a
regime boundary genuinely exists in the data. The problem is that **the
strategy never trades in trends at all.** It enters at *below-median*
efficiency on every interval: 1h all-bars median 0.174 against an entry median
of 0.137, and the most efficient bar it ever entered on scored 0.232 against an
all-bars p90 of 0.404.

The likely mechanical cause is already in the code: **the RSI-overbought filter
suppresses entries exactly when a clean directional move has driven RSI up.**
The strategy is structurally barred from entering the state this skill says it
should be trading in, which makes a regime filter largely redundant with a
filter the bot already has.

So a chop filter would not improve the strategy's trades. At ER ≥ 0.4 it
removes 58 of 59 of them, and any lower cutoff that keeps trades is a fitted
cutoff — the exact noise-fitting the protocol below exists to prevent.

Two further claims in the original text were stale rather than wrong, and are
retired with it: the "78–88% of the parameter space lost money" framing
predates the cost-model correction and the walk-forward work, and this skill
was written without knowledge that **buy-and-hold beats the strategy on every
interval**, which is a more fundamental problem than regime blindness.

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
4. **Test the mechanism, not just the P&L.** See *The mechanism check* below
   — it is now stated strategy-agnostically, because it generalises past
   regimes and because it is the step that refuted this skill.
5. **Report trade counts beside every result.** The prior sweep produced
   "+$0.47 on 3 trades." A filter that stands down most of the time will
   produce very few trades — and few trades cannot distinguish skill from
   luck, whichever direction they point.

Step 4 is the cheapest and most informative thing in this file. Do it
first, and be prepared for it to say no. It said no here.

## The mechanism check (general protocol)

Extracted to `.claude/skills/mechanism-check/SKILL.md` so it applies to any
conditioning idea, not just regimes. **Run it before any parameter search.**
The regime-detection hypothesis was refuted by this step; the protocol is the
durable output of that work.

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

Unreachable on the v0.1 momentum strategy rather than unmet — the first
condition below cannot be computed when one arm is empty. Kept as the bar for
whatever strategy reopens this skill.

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
