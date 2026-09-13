---
name: backtesting
description: Walk-forward backtesting protocol for TradeCC. Use when running, reviewing, or writing a backtest, or interpreting one's result. Enforces the fixed anti-overfit protocol and net-of-fees reporting so a result is usable evidence toward the live gate rather than a flattering number.
---

# Backtesting Protocol

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
net > 0; no single fold > 60% of pooled net; pooled trades ≥ 12. Any
failure → it did not replicate. Write that up and stop; do not widen the
grid or hunt for parameters that pass.

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
