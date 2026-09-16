---
name: backtesting
description: Walk-forward backtesting protocol for TradeCC. Use when running, reviewing, or writing a backtest, or interpreting one's result. Enforces the fixed anti-overfit protocol and net-of-fees reporting so a result is usable evidence toward the live gate rather than a flattering number.
---

# Backtesting Protocol

> **Not the same tool as `trade-simulation`.** A backtest asks "would this have
> made money"; `research/replay_sim.py` asks "does the machinery that places
> the trades work, and which branches has real data never reached". Its trade
> count is a coverage measure and is never evidence of edge. Edge questions
> stay here.


Every backtest follows this. Violations make the result unusable as
evidence for the live-trading gate. The protocol is not open to in-flight
revision — changing it is a decision record and a STOP.

## Hard rules

1. **Parameters frozen before results are seen.** Record them first in
   `research/backtests/YYYY-MM-DD_<strategy>_<summary>.md`, with the
   hypothesis, before running.

2. **Walk-forward: expanding window, 3 folds.** Fixed in
   `planning/decisions/2026-09-10-walk-forward-validation.md` — not
   rolling, not 5 folds. Report **every fold and the pool**, never the
   best fold alone. Harness: `research/walk_forward.py`. Phase A is the
   default-parameter baseline; Phase B (search over an initial train
   block) runs only when explicitly directed.

3. **Headline number is net of fees**, from the calibrated model at
   `src/execution/costs.py` — `CostModel.estimate(size, creates_token_account,
   sol_price_usd).total_usd`. It already models base fee, priority fee
   **per compute unit**, Jito tip, ATA rent (charged once per mint,
   refundable), and platform fee. Do **not** introduce a second fee model.
   Backtest adverse move splits into a measured `price_impact_pct` and an
   assumed `execution_slippage_pct` (`BacktestConfig`); the measured half
   is refreshed with `research/calibrate_costs.py`. Report the two
   separately so "how much of this is measured?" has an answer.

4. **Never cherry-pick date ranges.** State the range and its rationale in
   the file. The candle cache makes runs reproducible; re-running against
   silently different data is how a fake improvement appears.

5. **Trade count beside every P&L number.** "+$0.47 on 3 trades" is this
   repo's standing example of a number that looks like evidence and is
   not. A fold with <10 trades is weak evidence whatever its sign.

6. **Report:** expectancy/trade (net USD), win rate, max drawdown, trade
   count per fold and pooled. Profit factor / Sharpe only where the sample
   makes them meaningful — at current trade counts they usually do not.

## The locked decision rule (replication)

A result "replicates" only if **all** hold: net > 0 in ≥ 2/3 folds; pooled
net > 0; no single fold > 60% of pooled net; **pooled trades ≥ 19**. Any
failure → it did not replicate. Write that up and stop; do not widen the
grid or hunt for parameters that pass.

### Why 19, and why it used to say 12

**Changed 2026-09-16.** The minimum was 12, and 12 could not detect anything.

Detecting an edge at 95% confidence and 80% power takes
`n = 7.8489 × (σ/μ)²` round trips. This project has measured its own noise
ratio (σ ÷ E|move|) at **1.33–1.55** across assets, near-invariant
(`research/edge_budget.py`). That gives a floor of **13.88 round trips at the
most generous end, 18.86 at the other**.

Twelve was below the floor *at the generous end*, for a hypothetical perfect
strategy with no lag and no cost drag. A result that "replicated" on exactly
12 trades had not been detected — it had been guessed at, by a rule that said
otherwise.

**19 covers the measured range.** 14 would only be defensible if every future
strategy happened to trade the quietest asset in it, and a floor set at the
most flattering assumption is not a floor.

Two things worth keeping in view:

- **This is still a blanket constant standing in for a per-strategy
  quantity.** The honest test is `n > 7.8489 × (σ/μ)²` using *that
  strategy's own* measured noise. 19 is the conservative constant until
  someone wires the real computation into the report template.
- **No past result was invalidated by this change.** Every recorded verdict
  in `research/backtests/` is "did not replicate" — nothing ever passed, on
  12 trades or any other number. The rule was wrong, but it never let
  anything through.

Found by `research/copy_wallet/PHASE_A_VIABILITY_DRAFT.md` (Step 3), which
was checking copy-trading and hit the rule on the way past.

> ⚠️ **Open flag, 2026-09-16 — the pooled-12 minimum is below this project's
> own detection floor.** With the measured noise ratio (σ ÷ E|move| = 1.33 at
> its most generous end) and the standard 95/80 constant of 7.8489, detecting
> *any* edge takes `7.8489 × 1.33² = 13.88` round trips. Twelve is short of
> that by 1.88 trades — and 13.88 is the floor for a *perfect* strategy with
> no lag and no cost drag; a real one needs more.
>
> So a result that "replicates" on exactly 12 trades has not been detected at
> 95/80. It has been guessed at, by a rule that says otherwise. This is the
> error class `.claude/skills/edge-viability-check` exists to catch: a
> protocol rigorous about not fooling yourself on a *result*, while permitting
> a sample that cannot produce a trustworthy result either way.
>
> **This rule is locked and has deliberately not been changed here.** Raising
> it is the user's decision, not a side effect of the research draft that
> found it (`research/copy_wallet/PHASE_A_VIABILITY_DRAFT.md`, Step 3 and its
> review record). Until it is decided: treat a pass that rests on fewer than
> ~14 pooled trades as unproven regardless of what this rule permits, and say
> so in the write-up.

## Report template (end of every backtest file)

```
## Verdict
- Expectancy (net): $X/trade | Threshold: $Y | PASS/FAIL
- Per-fold net: [f0, f1, f2] | pooled: $Z (N trades)
- Max drawdown: X% | Threshold (pre-committed): Y% | PASS/FAIL
- Replication rule: PASS/FAIL (which condition failed, if any)
- Advances to paper gate: YES/NO
```

## Honesty caveat, carried into every report

A pass at these sample sizes means "not refuted", never "confirmed". No
arithmetic here turns ~15 trades into statistical significance. And a
replicated backtest is necessary for the live gate, never sufficient — the
gate (`src/core/gate.py`) additionally requires 30 paper days and a
drawdown threshold set before the run began.
