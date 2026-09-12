---
name: tradecc-risk-controls
description: Implement, strengthen, and unit-test risk controls for the Solana trading bot at github.com/youngstunners88/tradecc. Use when adding or fixing per-trade loss limits, daily loss circuit breakers, position size caps, slippage enforcement, or any code that must halt trading on threshold breach.
---

# Tradecc Risk Controls

Build and verify the load-bearing safety features of the tradecc bot. Risk controls must be enforced in code and proven by tests that actually stop trading when thresholds are crossed.

## Non-Negotiable Requirements

These come from the parent security skill and the repo’s CLAUDE.md / mvp_spec.md:

- Per-trade loss / stop-loss limit.
- Daily loss circuit breaker that **halts further trading** (not just logs).
- Hard position size cap (default $5–$10).
- Slippage cap enforced on every trade path.
- Controls live in the execution / risk path, not only inside strategy signal code.
- Unit tests must force the breach condition and assert that trading is halted.

## Workflow

### 1. Locate or Create the Risk Module
- Prefer a dedicated module under `src/` (e.g. `src/risk/` or inside `src/execution/`).
- All trade decisions must pass through the risk checks before any transaction is built or sent.

### 2. Required Controls (minimum set)

**Position size**
- Hard maximum in USD (or SOL equivalent).
- Reject any signal that would exceed it.
- Default remains the low validation size unless the user explicitly raises it via config and a decision record.

**Per-trade loss limit**
- Maximum acceptable loss on a single trade (absolute or % of position).
- Evaluated after fill / simulation or via stop logic.

**Daily loss circuit breaker**
- Running P&L (or realized + unrealized) tracked for the current UTC/local trading day.
- When the configured daily loss limit is reached or exceeded → call a clear `halt_trading()` (or equivalent) that prevents any further order placement until the next day or manual reset.
- Must be persistent across restarts within the same day (store state safely).

**Slippage**
- Enforced both at quote time and after simulation / fill.
- See also the parent skill’s Jupiter reference.

### 3. Implementation Principles

- Fail closed: if risk state cannot be read or updated, do not trade.
- Make the halt function explicit and easy to assert in tests.
- Log every trigger with enough context to reconstruct the decision (without leaking keys).
- Keep the risk layer independent of any single strategy so future strategies (copy-trade etc.) inherit the same protections.

### 4. Testing Requirements (mandatory)

For every risk control function:

```python
def test_daily_loss_breaker_halts_trading():
    # Arrange: set current daily PnL just below limit, then push it over
    risk = RiskManager(daily_loss_limit_usd=20.0)
    risk.record_pnl(-19.0)
    assert risk.can_trade() is True

    risk.record_pnl(-2.0)  # now -21
    assert risk.can_trade() is False
    # Optional: assert halt was called / state persisted
```

- Cover the exact threshold, just-under, and well-over cases.
- Cover reset behavior (new day).
- Cover interaction with position size and slippage checks.
- Never require a live network or real keys for these tests.

### 5. Output Expectations

When implementing or reviewing risk controls:
- Show the control surface (functions / config keys).
- Confirm each control has at least one test that proves it stops trading.
- Flag any path that can place a trade while a circuit breaker is open.
- Prefer small, focused changes that restore or strengthen the invariants.

## References

- `references/risk-control-test-template.md` — ready-to-adapt pytest structure that proves controls halt trading

## Relationship to Other Skills

- Parent: `tradecc-security` (overall threat model and non-negotiables).
- Sibling: `tradecc-paper-validation` (uses these controls as part of the live-readiness gate).

## Anti-Patterns

- Circuit breakers that only emit a log or metric.
- Risk checks that live only inside one strategy module.
- Tests that merely assert a warning was logged.
- Silently increasing position size or relaxing limits “to get trades through”.
