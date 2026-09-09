---
name: github-ci
description: Set up and maintain GitHub Actions CI for TradeCC — running the test suite and enforcing the coverage floor on every PR. Use this whenever adding or modifying tests, opening a PR, touching risk/execution/gate code, or whenever test count or coverage percentage changes. Always make sure CI is wired up and passing before treating a stage as "done" — a safety-critical trading bot must not merge code with an unverified test suite.
---

# GitHub CI for TradeCC

TradeCC is a money-adjacent codebase (live-trading gate, risk engine, key
handling). The test suite is not optional decoration — it's the thing
standing between a bug and a bad trade. CI exists to make sure nobody
(including an agent working fast) can merge past it by accident.

## When to use this skill
- Setting up CI for the first time.
- Any time the test count, coverage percentage, or CI workflow changes.
- Before opening a PR into `main` — confirm CI is configured and would
  actually run and block on failure.
- If asked to "speed things up" by skipping tests or CI on a PR — this is
  the moment to push back, not comply. Flag it to the user instead.

## What to set up
1. Copy `assets/test-workflow.yml` to `.github/workflows/test.yml` in the
   repo (adjust the Python version / package manager commands to match
   whatever this project actually uses — check `pyproject.toml` or
   `requirements.txt` first).
2. Set the coverage floor to **the current coverage number, not lower**.
   If the suite is at 94%, the workflow should fail if coverage drops
   below ~93% (a small buffer for rounding, not a free pass to regress).
   Raise the floor over time as coverage improves — never lower it
   without the user explicitly agreeing to accept a trade-off.
3. In GitHub repo settings, enable **branch protection on `main`**:
   require the CI check to pass before merge, and require the PR to be
   up to date with `main`. Do this via `gh api` or the GitHub API/token
   available in this environment rather than asking the user to click
   through the UI, then confirm it's actually active.
4. Every new risk-control test (stop-loss, daily circuit breaker, live-
   gate refusal, redaction) should run in CI, not just locally. If a
   safety-critical test is added but not wired into CI, treat that as an
   incomplete task.

## Reporting back to the user
When you finish a CI setup or update, state plainly: current test count,
current coverage %, the enforced floor, and whether branch protection is
actually on (verify — don't assume the API call succeeded). If anything
failed to apply, say so rather than reporting success.
