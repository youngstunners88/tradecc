# Regime detection — pre-registration check (the step-4 mechanism test)

**Date:** 2026-09-12
**Harness:** `research/regime_check.py`
**Prescribed by:** `.claude/skills/regime-detection/SKILL.md`, step 4 of its
anti-overfit protocol, run before any decision record fixes a protocol and
before any regime parameter is tried.

## What was asked

The skill's own instruction, verbatim:

> **Test the mechanism, not just the P&L.** Before optimising anything, check
> the claim directly: label the existing history by regime and compare
> expectancy in trend-labelled windows against chop-labelled windows, at the
> **default** parameters. If the gap is not there at defaults, regime
> conditioning is not the explanation, and tuning until it appears is fitting
> noise.

And: *"Step 4 is the cheapest and most informative thing in this file. Do it
first, and be prepared for it to say no."*

It said no.

## Verdict

**The regime hypothesis is untestable on this data, and its premise is
contradicted.** The trend arm is empty. A chop filter would not improve the
strategy's trades — it would delete all of them.

## Measurement

Kaufman efficiency ratio, window 20, the skill's own first-choice classifier.
Threshold ER ≥ 0.4 named before running, not fitted. Default parameters
(`fast_ema=12 slow_ema=26 rsi_period=14`), unchanged.

| Interval | bars | trades | ER median (all bars) | ER p90 | % bars TREND | label flips |
|---|---|---|---|---|---|---|
| 1h  | 1000 | 15 | 0.174 | 0.404 | 10.7% | 64 |
| 4h  | 1000 | 21 | 0.191 | 0.448 | 14.6% | 78 |
| 15m | 1000 | 23 | 0.126 | 0.329 |  6.6% | 34 |

A regime boundary **does** exist in the price data — labels flip 34–78 times,
so this is not a series stuck in one state. The problem is not the classifier.

Splitting the existing default-parameter trades by their entry-bar label:

| Interval | TREND arm | CHOP arm |
|---|---|---|
| 1h  | **n=0** | n=15, net +0.5815, expectancy +0.0388 |
| 4h  | **n=0** | n=21, net −0.5494, expectancy −0.0262 |
| 15m | n=1, net −0.1160 | n=22, net −1.6625, expectancy −0.0756 |

**One trade out of 59 was entered in a trend-labelled bar.**

## Why the arm is empty

The strategy does not merely trade in chop as often as anywhere else — it
systematically enters *below-median* efficiency:

| Interval | ER median, all bars | ER median at entries | ER max at entries |
|---|---|---|---|
| 1h  | 0.174 | 0.137 | 0.232 |
| 4h  | 0.191 | 0.109 | 0.372 |
| 15m | 0.126 | 0.079 | 0.432 |

On 1h the *most* efficient bar the strategy ever entered on scored 0.232,
against an all-bars p90 of 0.404. It never came close to a trend.

The likely mechanical cause is already in the code: the RSI-overbought filter
suppresses entries precisely when a clean directional move has driven RSI up.
The strategy is structurally barred from entering the state the regime
hypothesis says it should be trading in. A regime filter is therefore largely
redundant with a filter the bot already has.

## The post-hoc split, and why it does not rescue the hypothesis

Splitting instead at the median ER *of the trades themselves* — a threshold
chosen after seeing the data, reported here only so it is on the record and
cannot be presented later as a finding:

| Interval | median ER | high-ER arm | low-ER arm |
|---|---|---|---|
| 1h  | 0.137 | n=8,  exp +0.0156 | n=7,  exp +0.0652 |
| 4h  | 0.109 | n=11, exp −0.0277 | n=10, exp −0.0245 |
| 15m | 0.079 | n=12, exp −0.1067 | n=11, exp −0.0453 |

The higher-efficiency arm is **worse on all three intervals**. Even granting a
post-hoc threshold, n≈10 arms, and both arms sitting deep inside chop, the
gradient runs against the hypothesis rather than for it.

**Correction to an earlier figure.** A first pass at this split, reported in
conversation before this harness was written, used a shorter ER window and
showed 1h high-ER +0.111 against low-ER −0.044 — the hypothesis apparently
working. It does not survive the window change. That figure was
window-dependent and should be disregarded in favour of the numbers above,
which are reproducible from `research/regime_check.py`.

## What this forecloses

- **No regime decision record is proposed.** The protocol in the skill
  presupposes a comparison that cannot be made: one arm has no trades.
- **No regime threshold search.** The skill counts thresholds against the
  parameter budget, and searching for a cutoff that manufactures a non-empty
  trend arm is exactly the noise-fitting step 4 exists to prevent.
- **A chop filter is not a free improvement.** At ER ≥ 0.4 it removes 58 of 59
  trades. Any lower cutoff that keeps trades is a fitted cutoff.

## Where this leaves things

This is the sixth converging negative on the momentum strategy, and the first
to fail at the *mechanism* level rather than the P&L level. The previous five
said the strategy does not make money. This one says the most defensible
explanation offered for why — that it trades identically in trends and
ranges — is wrong in a specific way: **it does not trade in trends at all.**

That is a stronger and more useful result than another negative P&L. It
removes regime conditioning from the list of things worth trying on this
strategy, rather than leaving it open as untested.
