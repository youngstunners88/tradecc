# Decision: the max-drawdown threshold for the validation gate

**Date:** 2026-09-13
**Status:** **LOCKED at 8%, 2026-09-14.** Approved by the user on the derivation
below and written into `ops/live-gate.json` with
`threshold_set_at: 2026-09-14T00:41:03+00:00`. The gate remains **locked** — the
threshold was the only outstanding *decision*; the other five checks await
evidence that does not exist yet.

**The threshold is now immutable in the only way that matters.** `core/gate.py`
fails the gate when `threshold_set_at` is later than `paper_started_at`, so this
timestamp must predate the first paper tick. Moving it later to accommodate a
run that overshot would defeat the single thing the field exists for. If 8%
turns out to be the wrong number, the honest move is a new decision record and
a new paper run — not an edit to this one.

## Why this is not blocked on the strategy decision

`mvp_spec.md` has carried this as an open question since v0.1, and it has been
repeatedly deferred alongside strategy direction. That coupling was wrong.

A max-drawdown threshold answers **"how much of my money am I willing to watch
disappear before I conclude this was a mistake?"** That is a risk-tolerance
question about the operator, not a performance question about the strategy. It
has the same answer whether the thing being validated is momentum,
cross-sectional, copy-trading or something not yet invented — which is the
whole reason the gate demands it be set *before* the paper clock starts. A
threshold chosen after seeing results is a rationalisation, and `core/gate.py`
already enforces that by failing when `threshold_set_at` is later than
`paper_started_at`.

So it does not wait. Setting it now is also strictly safer than setting it
later: the later it is set, the more results exist to anchor it to.

## The arithmetic this number has to respect

Every figure below is computed from the configured defaults, not assumed:
`initial_capital_usd = $100`, `position_size_usd = $10`,
`per_trade_stop_loss_pct = 5`, `per_trade_take_profit_pct = 10`, and the
measured recurring fixed cost `F = $0.0127` per round trip.

| Quantity | Value |
|---|---|
| Worst per-trade net loss | $0.5127 → **0.5127%** of a $100 peak |
| Best per-trade net win | $0.9873 → 0.9873% |
| Reward:risk per round trip | 1.93 : 1 |

`max_drawdown_pct` (`src/core/performance.py:109`) is peak-to-trough on the
**per-closed-trade equity curve**, as a percentage of the running peak. It does
not see intra-trade excursion, so the stop-loss genuinely caps each step.

That makes drawdown structurally bounded by position sizing rather than by
market behaviour:

| Threshold | Dollars on $100 | Worst-case losing trades to reach it | Gain needed to recover |
|---|---|---|---|
| 3% | $3 | 5.9 | +3.1% |
| 5% | $5 | 9.8 | +5.3% |
| **8%** | **$8** | **15.6** | **+8.7%** |
| 10% | $10 | 19.5 | +11.1% |
| 15% | $15 | 29.3 | +17.6% |
| 20% | $20 | 39.0 | +25.0% |

## Finding 1 — the 15% placeholder is decoration, not a gate

`ops/live-gate.example.json` currently carries `max_drawdown_threshold_pct: 15`.
Reaching it takes a **net 29 worst-case losing trades**. Recorded backtests
produced max drawdowns of **1.24%** (first 1h run, 15 trades) and **0.53%–0.96%**
(capital-sensitivity, the one positive case). Walk-forward folds ran 10–15
trades each.

A threshold that sits ~24× above anything the system has ever produced cannot
fail. It would be a field that always passes, which is worse than no field at
all: it creates the appearance of a drawdown control while providing none.

## Finding 2 — the daily circuit breaker cannot protect this threshold

`daily_loss_limit_usd = $20` is **20% of the $100 capital base**. It takes 39
worst-case losing trades in a single UTC day to trip it.

So for any threshold worth setting, the drawdown limit binds *first* and the
breaker never fires on the way there. The two controls are calibrated against
different implicit bases — the breaker against a dollar figure, the gate against
a percentage of capital. This is not a bug in either, but it means **the
drawdown threshold is the only thing standing between a losing paper run and a
"passed" gate**, and it should be set with that weight in mind rather than as a
belt-and-braces second line.

## Finding 3 — the denominator is currently unpinned (must be fixed alongside)

`max_drawdown_pct` is a percentage of equity, and equity starts at
`backtest.initial_capital_usd`. That field is **not covered by
`validated_fingerprint`** — verified directly: changing it from $100 to $10,000
changes no fingerprint section.

The consequence: after an approval, raising the capital base divides every
observed drawdown percentage by the same factor, and the gate does not notice.
A 12% observed drawdown becomes 0.12% and clears an 8% threshold, with a
fingerprint that still matches.

**A percentage threshold against an unpinned denominator is not a gate.** This
is not a separate concern to schedule later; it is part of making this number
mean anything, so it is fixed in the same change: `capital_base` becomes a
fifth fingerprint section. Any gate file written before this change now fails
with `'capital_base' differs` and must be re-approved, which is the correct
fail-closed outcome for an approval that never pinned its own denominator.

## The proposal: 8%

### The rule used to pick it, stated before the number

> The threshold sits at **1.5× the drawdown implied by the expected longest
> losing streak, at the upper end of plausible trade counts** — far enough above
> ordinary variance that a working strategy will not trip it, close enough that
> a strategy without edge will.

Expected longest losing streak ≈ `log_{1/q}(N·p)` for `N` trades at win rate
`p`, `q = 1−p`. At the measured 40% win rate:

| Trades in the paper run | Expected longest losing streak | Implied drawdown |
|---|---|---|
| 50 | 5.9 | 3.01% |
| 100 | 7.2 | 3.70% |
| 200 | 8.6 | 4.40% |
| 400 | 9.9 | 5.09% |

A 30-day paper run at a 15m interval plausibly reaches the 200–400 band.
Taking the upper end: **1.5 × 5.09% = 7.6%, rounded to 8%.**

### Why not the neighbours

- **5% is inside the noise band.** At 400 trades and a 40% win rate the expected
  longest streak alone implies 5.09%. A threshold there fires on ordinary
  variance from a strategy that is working, and a gate that cries wolf gets
  worked around — the same reasoning that keeps `poll_seconds` out of the
  fingerprint.
- **10% and above discriminate less.** 10% needs ~20 net worst-case losses,
  which is deep into "this strategy is not working" territory; by the time it
  triggers, the expectancy check has almost certainly failed anyway. The
  threshold earns its place by catching the case where expectancy squeaks
  positive on a path that was violent getting there.
- **8% keeps recovery proportionate.** +8.7% to get back to peak. At 20% it is
  +25%, at 50% it is +100% — the region where a threshold is no longer
  protecting anything.

### In dollars, per rule 4 of the capital-sensitivity record

At the $100 base: **8% = $8**, or 0.8 of one position. At a $1,000 base the same
8% is $80. The percentage is the gate; the dollar figure is what the operator
actually feels, and both are stated because the percentage alone hides the
difference.

## What locking this required — and what is done

1. ~~The user confirms 8%~~ — **done, 2026-09-14.**
2. ~~`max_drawdown_threshold_pct` written into `ops/live-gate.json` with
   `threshold_set_at`~~ — **done**, `2026-09-14T00:41:03+00:00`. The file is
   committed as an audit record and contains *only* the threshold; every other
   field is absent, so the gate reports seven failures and stays locked.
3. The paper run must start **after** that timestamp. `_check_drawdown` fails
   the gate if `threshold_set_at > paper_started_at`, so the ordering is
   enforced, not merely intended. **Still outstanding** — no paper run has
   started.
4. The fingerprint must be regenerated, now including `capital_base`. **Still
   outstanding** — there is nothing to approve yet.

## What this record does NOT do

- **It does not unlock anything.** Writing the threshold satisfied one decision,
  not one gate check with evidence behind it. `tradecc gate` still exits 2.
- **It does not start a paper run** or authorise live trading. The gate's other
  five checks are untouched and none of them currently pass.
- **It does not reopen Stage 6c/6d**, which remains stood down pending an
  explicit instruction naming it.
- **It does not change any risk default.** `daily_loss_limit_usd`,
  `position_size_usd` and the stops are exactly as they were; Finding 2 is an
  observation about how they interact, not a proposal to retune them.
