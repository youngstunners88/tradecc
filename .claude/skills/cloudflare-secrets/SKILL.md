---
name: cloudflare-secrets
description: Use Cloudflare as the secrets store for TradeCC's wallet key, and evaluate Cloudflare Pages/Workers for hosting only where they actually fit. Use this whenever wiring up wallet key loading, deciding where secrets live, or resolving the "where does this run" open question from planning/specs/mvp_spec.md. Always use a scoped Cloudflare API Token here, never the Cloudflare Global API Key — that key has full account access and is too high-blast-radius to hand to an automated process for a money-adjacent project.
---

# Cloudflare for TradeCC — Secrets, Not the Whole Stack

## Security rule (non-negotiable, ties to CLAUDE.md rule 1 and 2)
If both `CLOUDFLARE_API_KEY` and `CLOUDFLARE_GLOBAL_API_KEY` are present
in the environment, **only ever use the scoped API Token
(`CLOUDFLARE_API_KEY`)**. The Global API Key grants full account access
— DNS, billing, every zone — and should not be reachable by an
automated coding/trading agent. If the scoped token doesn't have the
permission needed for a task, that's a signal to request a
better-scoped token, not to fall back to the Global key.

## What Cloudflare is good for here
- **Secrets storage for the wallet key** — Cloudflare's Secrets Store
  (or Workers KV, if the execution process runs as a Worker) fits the
  "secrets manager" requirement in `ops/CONTEXT.md`. The bot process
  reads the key at runtime; it is never written into the repo or a
  `.env` that gets committed.
- **A future status page / webhook receiver** — Cloudflare Pages can
  host a lightweight status page later, if PostHog's built-in
  dashboards genuinely don't cover what's needed. Don't build this
  preemptively — check with the user first (see the
  `posthog-observability` skill).

## What Cloudflare is probably NOT good for here
- **Running the main bot loop.** Cloudflare Workers have execution-time
  limits that don't fit a persistent trading loop that needs to hold
  state, poll prices, and react continuously. The main process likely
  needs an always-on host (VPS or similar) — this is still an open
  question in `planning/specs/mvp_spec.md`; don't resolve it by
  defaulting to Workers without flagging the fit problem to the user.

## Before wiring this up
Confirm with the user:
1. Which Cloudflare product they actually want for secrets (Secrets
   Store vs. Workers KV) — depends on whether any part of the stack ends
   up running on Workers.
2. That the token in use is scoped, not the Global key — verify this
   explicitly rather than assuming based on the variable name.
