Read CLAUDE.md at the root of this repo first — it has the identity,
routing table, stack decisions, and seven non-negotiable safety rules
for this project. Then read planning/CONTEXT.md and
planning/specs/mvp_spec.md, which define exactly what v0.1 is.

This is a Solana trading bot. It trades at small position sizes
($5–$10) and defaults to paper trading — simulated fills against real
market data, no real transactions sent — until it clears an explicit
validation gate defined in the spec. Do not build live-trading
execution that bypasses that gate.

Before writing any code:
1. Confirm the open questions in planning/specs/mvp_spec.md with me —
   especially Python vs. TypeScript (the repo currently assumes Python;
   tell me if you'd build this differently in TypeScript and why, and
   I'll decide), the OHLC/price data source for backtesting, and where
   this will eventually run.
2. Propose a short build plan broken into stages that match the src/
   structure (execution, strategy, risk, tests) — I want to review the
   plan before you start writing files, not after.

Once I confirm the plan, scaffold src/ per src/CONTEXT.md, starting
with the risk module and a mocked execution layer before wiring up real
Jupiter/Helius calls — I want the safety controls (slippage cap,
per-trade stop-loss, daily circuit breaker) built and unit-tested
first, with everything else built against them, not bolted on after.

Reference implementations worth looking at for patterns (not for
copy-pasting wholesale — read planning/decisions/2026-09-09-strategy-
and-stack.md for why each is or isn't trustworthy as-is):
- github.com/moondevonyt (moon-dev-ai-agents) — Jupiter execution
  snippets and the RBI backtesting pattern. Explicitly not profitable
  out of the box per its own README.
- nmweaver/soltrade — minimal Python TA (EMA/RSI/Bollinger) + Jupiter
  integration, close to what our v0.1 strategy module needs.
- outsmartchad/solana-trading-cli (aka outsmart-cli) — reference for
  execution/transaction-landing patterns if plain Jupiter calls aren't
  enough.

Ask me anything that's genuinely ambiguous rather than guessing on
anything touching money movement, key handling, or the risk controls.
