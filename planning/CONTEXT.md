# Planning — CONTEXT.md

## What happens here
This is where scope, strategy, and architecture get decided *before*
code gets written. If you (Claude Code) are about to make a call on
"which strategy," "which library," or "what's in scope for this
version" — check here first. If it's not written down, ask the user
rather than assuming.

## What's in this workspace
- `specs/mvp_spec.md` — the spec for the current build target (v0.1).
  This is the source of truth for what to build right now.
- `architecture/` — diagrams, module boundaries, data flow notes as the
  system grows. Empty at project start; fill in as decisions get made.
- `decisions/` — dated decision records (ADR-style). Each one is a
  snapshot of a choice and the reasoning behind it. Don't edit old ones;
  add a new dated file when a decision changes, and reference the one it
  supersedes.

## Process
1. New feature or strategy idea → write or update a decision record in
   `decisions/` first if it changes strategy, chain, or stack.
2. Once scope is settled, `specs/mvp_spec.md` (or a new versioned spec)
   gets updated to reflect it.
3. Only then does work move to `/src`.

## Rules specific to this workspace
- Never silently expand scope (e.g., adding arbitrage or a second chain)
  without a decision record explaining why and confirming with the user
  — the research behind this project found those paths to be
  unfavorable at current capital levels.
- Keep specs honest about what's *not* built yet. A spec that claims
  live-trading readiness before the validation gate is met is a bug in
  the spec, not just the code.
