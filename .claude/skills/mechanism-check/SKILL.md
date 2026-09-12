---
name: mechanism-check
description: Strategy-agnostic pre-registration probe. Run this BEFORE any parameter search on any conditioning idea — regime, liquidity band, time of day, funding rate, wallet cohort, sentiment, anything. It costs one backtest and it is the only step that can refute a conditioning idea before a parameter search makes it unfalsifiable. Extracted from regime-detection after that hypothesis was refuted by this exact step.
---

# The mechanism check

A conditioning idea says: *the strategy behaves differently in state A than in
state B, and we should act on that difference.* Before you tune a threshold,
before you write a decision record, before you touch a parameter, run this.
It is one backtest at defaults. It is the cheapest and most informative step
in the whole workflow, and it is the only step that can kill an idea cleanly.

The regime-detection hypothesis was refuted by this step: 1 of 59 trades
landed in the trend arm, so the premise ("the strategy earns in trends and
bleeds in ranges") was contradicted before any threshold was tried. That is a
stronger result than a negative P&L, because it removes the idea from the list
rather than leaving it open as untested.

## When to run it

Run it whenever any of these is proposed:

- A new state variable to condition on (regime, liquidity band, time of day,
  funding rate, wallet cohort, sentiment, volatility bucket, …).
- A new filter that suppresses trades the strategy already proposes.
- A new "the strategy only works when X" claim, from any source — including
  a model, including yourself.

Do **not** run it after a parameter search. Running it after is fitting noise
with extra steps.

## The protocol

1. **Name the state variable and its split point in advance, in writing.**
   A cutoff chosen after seeing the split is a fitted parameter, not a filter.
   Record it in a decision record under `planning/decisions/` before computing
   anything.

2. **Run the strategy at default parameters over existing history.** Change
   nothing. The check is about where the strategy *already* trades, not about
   what it could be tuned to do. Tuning first and checking second inverts the
   logic.

3. **Label each trade by the state variable at its entry bar**, computed from
   closed candles up to and including that bar only. No look-ahead. The label
   at bar N uses `candles[:N+1]`.

4. **Check both arms are non-empty first.** An empty arm means the hypothesis
   is *untestable on this data*, not that it failed. Untestable is where you
   stop — there is nothing to compare, and any threshold that produces a
   non-empty arm is a fitted threshold.

5. **Compare expectancy across arms, with trade counts beside every number.**
   A gap on n<10 per arm is not a gap. Report net-of-cost, not gross.

6. **Report the answer whichever way it falls**, in `research/backtests/`,
   following the naming convention
   `YYYY-MM-DD_<strategy>_<summary>.md`. A post-hoc split may be reported
   alongside, but only labelled as post-hoc, so it cannot later be presented
   as a finding.

## Reading the result

- **Gap present at defaults, both arms non-empty, n≥10 per arm.** The idea
  survives the mechanism check. It is now eligible for a decision record and
  a parameter search — under the anti-overfit protocol in
  `regime-detection`, which still applies.
- **No gap at defaults.** The conditioning idea is not the explanation.
  Tuning until the gap appears is fitting noise. Stop.
- **One arm empty.** The premise is contradicted. This is the strongest
  possible negative result: it removes the idea from the list rather than
  leaving it open as untested. Write it up and stop.

## What this protocol is not

- It is not a substitute for out-of-sample validation. Passing the mechanism
  check means the idea is *testable*, not that it is *true*.
- It is not a substitute for the anti-overfit protocol. A surviving idea still
  needs a pre-registered decision record, a fixed grid, a fixed selection
  rule, a minimum trade count, and a stopping rule.
- It is not a P&L test. It is a premise test. A premise can be true and the
  idea still not pay after costs.

## Reference implementation

`research/regime_check.py` is the worked example: Kaufman efficiency ratio,
window 20, threshold 0.4 named before running, every interval reported, no
threshold fitted, no configuration selected. Copy its shape for a new state
variable — the classifier changes, the protocol does not.

## Relationship to other skills

- `regime-detection` — the hypothesis this protocol refuted. Its anti-overfit
  rules still bind any idea that survives this check.
- `backtesting` — the harness this protocol runs on.
- `astra-analyst` — a hypothesis from Astra is worth exactly as much as one
  from anywhere else: nothing until it survives this check and then
  out-of-sample validation.
