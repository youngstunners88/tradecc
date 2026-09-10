---
description: Audit whether the live-trading validation gate is met before live mode is enabled
---

Audit the validation gate from `planning/specs/mvp_spec.md`. You are a
gatekeeper, not a helper — your job is to find reasons to say NO. The gate
is enforced in code at `src/core/gate.py` (`evaluate_live_gate`), reads
`ops/live-gate.json` (template: `ops/live-gate.example.json`), and **fails
closed**: any missing or unreadable field leaves live mode locked.

## Checklist (verify each against evidence, not claims)

1. [ ] **≥ 30 days of paper trading.** The gate measures this from
       `paper_started_at` → `paper_ended_at` in `ops/live-gate.json`, not
       a per-day log (there is no `research/paper-log/`). The live paper
       session state lives at `<state_dir>/paper-session.json`; confirm
       the timestamps trace to a real run, and that `started_at` was never
       reset by a restart.
2. [ ] **Net-of-fees expectancy > 0** over the paper period —
       `net_expectancy_usd`, recomputed from evidence, not a summary.
3. [ ] **Max drawdown within a pre-committed threshold.** The gate
       requires `threshold_set_at` to predate `paper_started_at`; a
       threshold recorded after the run began fails by design. Confirm the
       threshold traces to a dated decision record.
4. [ ] **Risk controls block, not just log.** Slippage cap, per-trade
       stop-loss, daily circuit breaker, position size — each has a test
       asserting the trade is rejected/halted. Run the risk-audit skill.
5. [ ] **Every live path simulates before sending.** Grep the path
       reachable from `BOT_MODE=live` for bypasses, TODOs, or test-only
       shortcuts. (Note: live execution is Stage 6 and not yet built; the
       gate and `PaperTrader`'s live-refusal are what exist today.)
6. [ ] **Key handling** matches `ops/CONTEXT.md`: env/secrets manager,
       nothing in git, nothing in logs. The `block-secrets` PreToolUse
       hook is a backstop, not the audit.
7. [ ] **Incident log** has an entry for every circuit-breaker trip and
       unexpected loss, with root cause (`ops/incident-logs/`).
8. [ ] **`PYTHONPATH=src python -m cli gate` reports unlocked**, and
       `PYTHONPATH=src python -m cli live` refuses cleanly when it should.

## Output

- **VERDICT: GATE PASS / GATE FAIL**, each check marked
  PASS / FAIL / EVIDENCE-MISSING.
- If FAIL: list exactly what evidence is missing and how to produce it.
- If PASS: draft (do **not** commit) a dated
  `planning/decisions/YYYY-MM-DD-live-gate-approval.md` for the user to
  review and merge. Approval is the user's, never yours to grant.
