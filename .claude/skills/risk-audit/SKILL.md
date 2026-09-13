---
name: risk-audit
description: Audit any change touching src/risk, src/execution, mode selection, or key handling before it is considered done. Use after modifying risk controls, execution, the cost model, or the live gate. Verifies controls block rather than merely log, and that no path bypasses risk or the gate.
---

# Risk Audit Checklist

Run after ANY edit to `src/risk/`, `src/execution/`, mode selection, the
cost model, or key handling.

1. **Veto power intact.** `execution/` (and the backtest/paper runners)
   call `RiskEngine.approve()` before every send/fill path, including
   error and early-return branches. A bypass in one branch is a bypass.
   Risk runs in *every* mode — backtest and paper included — or the paper
   run is evidence about a more permissive system than live.

2. **Tests prove blocking, not logging.** Each control (slippage cap,
   per-trade stop-loss, daily circuit breaker, position size) has a test
   asserting the trade is REJECTED or trading HALTS. A test that only
   asserts a warning was logged FAILS this audit.

3. **Live path simulates before sending.** From `BOT_MODE=live` config
   load to send, exactly one path exists and it runs
   `simulateTransaction` before signing, with no `if testing:` branch
   reachable from live. (Live execution is Stage 6 and not yet built;
   today the checks are that the gate refuses and `PaperTrader` refuses
   construction in live mode.)

4. **Gate enforced in code.** The live gate is `src/core/gate.py`
   (`evaluate_live_gate`), reads `ops/live-gate.json`, and fails closed.
   `PYTHONPATH=src python -m cli live` must refuse whenever the gate is
   unmet. There is **one** gate implementation — do not add a parallel
   script- or JSON-driven gate beside it.

5. **Cost model is the single one.** Fees/slippage come from
   `src/execution/costs.py` (`CostModel`). No second fee model, and no
   hardcoded market constant reintroduced (SOL price is passed in per bar
   or fetched live, never fixed in config as a truth).

6. **No secrets.** Keys load only from env/secrets manager; nothing
   key-shaped in new code, logs, or test fixtures. The `block-secrets`
   PreToolUse hook is a backstop, not a substitute for this check.

7. **No silent size changes.** Position size defaults stay $5–$10; any
   increase requires the explicit `position_size_override_ack` in config
   and a decision record (CLAUDE.md rule 6).

If any check fails, report it and **stop** — surface it to the user
rather than fixing silently and continuing. That escalation is the point
of the audit.
