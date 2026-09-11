# Decision: External Repo Evaluation Round 2 (2026-09-10)

## Context
Ten additional repos were proposed for evaluation. None are adopted for
execution. This record exists so the reasoning isn't lost and isn't
re-litigated if any of these come up again.

## Rejected, with reasoning worth remembering
- **`ghostwright/phantom`** — an autonomous agent explicitly designed to
  act without asking permission and self-modify its own configuration.
  This is not a component gap, it's a direct contradiction of this
  project's core posture (propose-first, narrow scope, human approval
  before scope changes). Do not reconsider this one without a full
  re-read of `CLAUDE.md`'s non-negotiable rules.
- **`NoFxAiOS/nofx`** — a trading terminal where an LLM decides trades
  directly, with real exchange funds. This is the precise pattern
  `astra-analyst`'s "proposes, deterministic Python disposes" design
  was built to avoid. Useful as a named counter-example, not as code.

## Reference-only, not dependencies
- **`TauricResearch/TradingAgents`** — credible, actively maintained,
  explicitly research-only per its own maintainers. Its debate-then-
  veto agent architecture (analyst team → bull/bear researcher debate →
  trader → risk manager approval) is close to what `astra-analyst`
  needs structurally. Its recent releases fixing look-ahead/point-in-
  time bias bugs are also a prompt to audit our own walk-forward
  harness for the same bug class. See
  `planning/architecture/tradingagents-reference-notes.md`.
- **`freqtrade/freqtrade`** and **`jesse-ai/jesse`** — mature,
  CEX-focused (ccxt) Python trading frameworks. Cannot execute Solana
  DEX trades through them, so not a dependency. Their hyperopt/
  walk-forward tooling is a useful maturity bar to check our hand-built
  harness against. See
  `research/backtest-methodology-references.md`.

## Parked, no action needed
- **`VinvAI/VinvAI`** — general Python runtime-tracing/testing tool,
  unrelated to trading. Paid product after trial. Not pursued.
- **`AI4Finance-Foundation/FinRL`** — a genuinely different strategy
  class (reinforcement learning). Real scope, not what v0.2 greenlit.
  If ever pursued, needs its own decision record and propose-first
  gate, same as copy-trading did.
- **`browser-use/browser-use`** — unchanged from the earlier
  evaluation; gated to `web-research-vetting`, v0.2 wallet research
  only.
- **`moondevonyt/moon-dev-ai-agents-for-trading`** — same project
  already evaluated (kept as reference, never run live). No change.

## Selective evaluation recommended, not urgent
- **`jiayaoqijia/cryptoskill`** — a large (977-skill) community
  registry, curated with a static/security risk gate. Includes Helius,
  Jupiter, and DEXScreener skills. Given the trust surface of a
  977-contributor registry, the right approach is pulling and reading
  **specific named skills** individually if a real need arises — not
  bulk-installing the registry. Not urgent: we already have working,
  measured Jupiter/Helius integration.
