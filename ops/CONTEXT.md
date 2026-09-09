# Ops — CONTEXT.md

## What happens here
Deployment, monitoring, key-management operations, and incident
handling once the bot is running anywhere outside a local test run.

## What's in this workspace
- `deploy/` — how and where the bot runs (local vs. VPS — TBD, see open
  question in the MVP spec). Deployment scripts/config go here, never
  secrets themselves.
- `monitoring/` — how you'll know if the bot is doing something wrong:
  log review process, alerting rules (e.g., alert on repeated RPC
  failures, alert if the daily circuit breaker triggers), and where logs
  live.
- `incident-logs/` — one dated file per incident (unexpected loss,
  circuit breaker trip, RPC outage, a bug that caused a bad trade).
  Write these even for small incidents — patterns matter more than any
  single event.

## Required key-management pattern
1. The wallet key is generated once, dedicated to this bot, and funded
   only with capital the user can afford to lose.
2. The key is stored in a secrets manager (preferred) or an env var
   injected at runtime on a locked-down host (minimum acceptable) —
   never in a file inside this repo, never in a commit, never in a log
   line.
3. `.env.example` in the repo root shows the *shape* of required config
   (variable names only) — it must never contain a real value.
4. If capital grows meaningfully beyond the $5–$10 validation phase,
   revisit this for a managed-signing/KMS approach — not required for
   v0.1.

## Operational rules
- No deployment to a live-money mode until the validation gate in
  `planning/specs/mvp_spec.md` has been met and confirmed with the user.
- Every circuit-breaker trip or unexpected-loss event gets an incident
  log entry, even if the cause turns out to be minor.
- Position size only increases with explicit user confirmation, logged
  as a decision — never auto-scaled by the bot itself.
- Before any change to `ops/deploy` that affects how the live wallet key
  is accessed, re-read the key-management pattern above and confirm the
  change doesn't weaken it.
