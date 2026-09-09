# Research — CONTEXT.md

## What happens here
Backtesting, strategy validation, and (later) wallet-candidate research
for copy-trading v0.2. This is where you find out *whether the strategy
actually works* before it ever touches real money.

## What's in this workspace
- `backtests/` — one dated file per backtest run. Include: the
  parameters used, the date range and data source, gross P&L, P&L
  **after modeled fees/slippage** (this is the number that matters —
  gross P&L is misleading at $5–$10 sizes), max drawdown, and win rate.
- `wallet-tracking/` — not used in v0.1. Reserved for v0.2 copy-trading
  research: candidate wallets, their win rate, max drawdown, median hold
  time, and any red flags (e.g., wash-trading patterns, high rug-token
  ratio). Do not build copy-trading execution against a wallet that
  hasn't been logged and evaluated here first.

## Process for a backtest
1. Define parameters and date range before running (avoid tuning after
   the fact on the same data you're evaluating against — that's
   overfitting).
2. Run against real historical data via the chosen data source (see
   open question in `planning/specs/mvp_spec.md`).
3. Log results in `backtests/YYYY-MM-DD_<strategy>_<summary>.md`
   including fee/slippage-adjusted numbers, not just gross.
4. Only strategies that clear the expectancy and drawdown thresholds set
   in the MVP spec move toward the paper-trading validation gate.

## Rules specific to this workspace
- Always report P&L **net of realistic fees and slippage** alongside
  gross — a strategy that's profitable gross but not net is not
  profitable at this position size.
- Don't cherry-pick date ranges to make a strategy look better. Note the
  date range and rationale for choosing it in every backtest file.
- Wallet-tracking entries (v0.2, later) must include the red flags
  identified in the project's research — win rate, drawdown, and
  suspicious trading patterns — before a wallet is considered a copy
  candidate.
