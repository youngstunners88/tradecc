---
description: Produce a staged, spec-first, risk-first implementation plan before any code is written
---

You are planning a change to TradeCC, a Solana trading bot. Follow the
repo's own process — do not skip stages, and do not write code in this
command. Planning only.

## Rules

1. **Scope/strategy/stack changes need a decision record first.** If the
   change touches strategy, chain, stack, or a safety control, draft a
   dated ADR in `planning/decisions/YYYY-MM-DD-<topic>.md` (context,
   decision, consequences, what it supersedes) and put it to the user for
   confirmation **before** writing anything else. This repo's history is
   emphatic on one point: a decision record that ships alongside the work
   it authorizes is a rationalisation, not a gate. Write it first, alone.

2. **New functional requirements update the spec first.** If the change
   is a new requirement, update `planning/specs/mvp_spec.md` (or propose
   a versioned spec) before touching `src/`.

3. **Then produce a staged plan matching `src/CONTEXT.md`.** Risk-first,
   because `risk/` has veto power over every mode:
   - **Stage 1 — `src/risk/` + `src/execution/costs.py` + tests.** Risk
     controls (sizing, slippage cap, stops, daily circuit breaker) and
     the fee/cost model come first. The cost model already exists at
     `src/execution/costs.py` (`CostModel`) and is calibrated — extend
     it, do not recreate it, and never add a second fee model.
   - **Stage 2 — `src/strategy/` + tests.** Pure functions of closed
     candles: no I/O, no clock, no randomness.
   - **Stage 3 — `src/execution/` against injected fakes + tests.** The
     HTTP transport is the mock boundary; unit tests never touch the
     network.
   - **Stage 4 — real execution wiring**, simulate-before-send enforced.
     This is Stage 6 in the project's own numbering and is gated.

4. **For each stage:** list exact files, the tests that must pass, and
   what "done" means (green suite + coverage floor held).

5. **Flag any conflict with the 7 non-negotiable rules in `CLAUDE.md`
   and STOP** if found — do not plan around them.

6. **Wait for explicit approval before implementing any stage.**

The task: $ARGUMENTS
