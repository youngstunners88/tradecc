---
description: Run a rigorous walk-forward backtest under the repo's fixed anti-overfitting protocol
---

Run a backtest following `research/CONTEXT.md`, the `backtesting` skill,
and the walk-forward protocol already fixed in
`planning/decisions/2026-09-10-walk-forward-validation.md`. Do not
shortcut it, and do not invent a new protocol — one exists.

## Protocol

1. **Freeze parameters before running.** Record them in a new
   `research/backtests/YYYY-MM-DD_<strategy>_<summary>.md` with the
   hypothesis stated **before** results are seen.

2. **Walk-forward validation is mandatory.** The fixed structure is
   **expanding window, 3 folds** — not rolling, not 5. The reasons
   (limited history, matching live retrain, avoiding a window-length
   parameter) are in the decision record; if you believe the structure
   should change, that is a new decision record and a STOP, not an
   in-flight edit. Report **every fold**, never the best one. The harness
   is `research/walk_forward.py`.

3. **Net-of-fees is the headline.** Costs come from the calibrated model
   at `src/execution/costs.py` (`CostModel.estimate(...).total_usd`),
   which already models base fee, priority fee **per compute unit**, Jito
   tip, ATA rent (once per mint), and platform fee. Backtest adverse move
   is split into a measured `price_impact_pct` and an assumed
   `execution_slippage_pct` (`BacktestConfig`); refresh the measured
   inputs with `research/calibrate_costs.py`. Gross P&L is context, never
   the verdict.

4. **Report:** expectancy per trade (USD), win rate, max drawdown, trade
   count — **trade count beside every P&L number**, because this repo has
   been burned by "+$0.47 on 3 trades." Profit factor and Sharpe only
   where the sample makes them meaningful; at these trade counts they
   usually do not.

5. **Apply the locked decision rule** from the decision record (net > 0
   in ≥2/3 folds; pooled net > 0; no fold > 60% of pooled net; pooled
   trades ≥ 12). Any failure → "did not replicate", write it up, stop.

6. **Honest verdict:** PASS / FAIL / INCONCLUSIVE against the thresholds
   in `planning/specs/mvp_spec.md`, and whether this advances toward the
   paper-trading gate. A replicated backtest is necessary for the gate,
   never sufficient — the gate additionally needs 30 paper days and a
   pre-committed drawdown threshold (`src/core/gate.py`).

The strategy/parameters to test: $ARGUMENTS
