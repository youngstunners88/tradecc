---
name: tradecc-paper-validation
description: Enforce and evaluate the paper-trading validation gate for the Solana trading bot at github.com/youngstunners88/tradecc before any live trading is unlocked. Use when checking readiness for live mode, reviewing paper results, defining max-drawdown thresholds, or confirming the mvp_spec validation gate has been met.
---

# Tradecc Paper Validation

Protect capital by ensuring the bot only moves to live trading after a rigorous, documented paper-trading period that demonstrates positive expectancy under realistic conditions.

## Source of Truth

- `planning/specs/mvp_spec.md` — contains the official validation gate.
- Top-level `CLAUDE.md` non-negotiable rules.
- Any decision records under `planning/decisions/` that define drawdown limits or parameter changes.

## Validation Gate (must all be true)

From the current mvp_spec (confirm latest text):

1. Minimum **30 days** of continuous `paper` mode running against real market conditions.
2. Strategy shows **positive expectancy after modeling realistic fees, slippage, and Jupiter fee tiers** (not just gross P&L).
3. Max drawdown during the paper period stays within a threshold the user set **before** the test started (recorded in a decision record).
4. Only after the above pass may `live` mode be unlocked, and even then it starts at the $5–$10 default position size.

Additional hard requirements before unlocking live:
- All risk controls (see `tradecc-risk-controls`) are implemented and have tests that prove they halt trading.
- Key handling follows the safe patterns (no hard-coded secrets, dedicated hot wallet).
- Every trade path still simulates before send.
- Incident logging process exists under `ops/`.

## Workflow

### 1. Confirm Gate Status
- Read the latest `planning/specs/mvp_spec.md` and any superseding decision records.
- Determine current bot mode and whether live is still code-gated.
- Check for existing paper-trading logs / backtest summaries under `research/`.

### 2. Define or Verify Pre-Test Parameters
- Max drawdown threshold must be chosen and written down **before** the 30-day clock starts.
- Position size, slippage cap, daily loss limit must be fixed for the paper period (or changes logged as new decisions).
- Record the start date and configuration snapshot.

### 3. Evaluate Paper Results
When reviewing paper results ask:
- Is the period ≥ 30 calendar days of real-market paper trading?
- After subtracting realistic fees + slippage + Jupiter tiers, is expectancy still positive?
- Did realized max drawdown stay inside the pre-agreed limit?
- Were risk controls triggered appropriately (and did they halt as designed)?
- Are there unexplained gaps, missing logs, or periods where the bot was offline?

### 4. Unlock Decision
- Only the user can authorize unlocking live mode after the gate is met.
- Record the unlock (or rejection) as a dated decision under `planning/decisions/`.
- Even after unlock, keep the default position size small and the circuit breakers active.

### 5. Output Expectations
- Clear pass / fail / incomplete status against each gate criterion.
- List of missing evidence or open questions.
- Recommendation: remain in paper, extend the period, adjust parameters (with new decision record), or proceed to gated live.

## References

- `references/gate-checklist.md` — printable checklist for the paper → live decision

## Relationship to Other Skills

- Parent: `tradecc-security`.
- Companion: `tradecc-risk-controls` (risk controls are a prerequisite for a meaningful paper period).

## Anti-Patterns

- Starting the 30-day count after the fact or changing the drawdown limit after seeing results.
- Claiming “positive expectancy” on gross P&L while ignoring fees and slippage.
- Unlocking live mode in code before the user has confirmed the gate is met.
- Running paper mode with risk controls disabled “to see pure strategy performance”.
