# External Tools & Repos Registry

Single source of truth for every external tool, repo, and connector
evaluated for TradeCC. Read this before installing, wiring in, or
reconsidering any of the tools below — it exists so past reasoning
doesn't get re-litigated or silently reversed. Update this file in the
same commit whenever a status changes.

**Status key:** ADOPTED (live in the repo) · ADOPTED-PENDING (built,
not wired) · GATED (v0.2+, needs explicit greenlight) · EVALUATING (no
decision yet) · REJECTED (do not reconsider without re-reading the
reasoning) · PARKED (not relevant now, no verdict needed)

---

## ADOPTED — live in the repo

| Tool | Link | What it's for | Where it lives |
|---|---|---|---|
| GitHub Actions CI | github.com (native) | Test suite + coverage floor enforced on every PR | `.claude/skills/github-ci/`, `.github/workflows/test.yml` |
| PostHog | posthog.com | Redacted trade/risk/mode-change events, dashboards | `.claude/skills/posthog-observability/` |
| Cloudflare (scoped token only) | cloudflare.com | Wallet-key secrets store. **Never the Global API Key** | `.claude/skills/cloudflare-secrets/` |
| Helius | helius.dev | Solana RPC (free tier) | `src/execution/` |
| Jupiter | jup.ag (`lite-api.jup.ag`) | Swap quotes/routing (free tier, keyless) | `src/execution/` |
| BIP-39 wordlist mnemonic matcher | bitcoin/bips (wordlist source) | `block-secrets.py` PreToolUse hook, wired in `settings.json` | `.claude/hooks/block-secrets.py` |
| plan-stage / backtest / ship-gate commands, backtesting / risk-audit skills | (adapted from a pasted third-party kit, rewritten to match this repo) | Process formalization: spec-first, walk-forward protocol, adversarial gate audit | `.claude/commands/`, `.claude/skills/backtesting/`, `.claude/skills/risk-audit/` |
| TauricResearch/TradingAgents | github.com/TauricResearch/TradingAgents | **Reference only, never installed.** Debate-then-veto multi-agent pattern informing `astra-analyst`; also flagged the look-ahead-bias bug class we audited for | `planning/architecture/tradingagents-reference-notes.md` |
| freqtrade/freqtrade | github.com/freqtrade/freqtrade | **Reference only, never installed.** CEX-focused, can't execute Solana trades — used as a maturity check on our walk-forward/hyperopt discipline | `research/backtest-methodology-references.md` |
| jesse-ai/jesse | github.com/jesse-ai/jesse | **Reference only, never installed.** Same treatment as freqtrade | `research/backtest-methodology-references.md` |

## ADOPTED, PENDING WIRING

| Tool | Link | Status |
|---|---|---|
| AgentMail | agentmail.to | Skill built (`agent-mail-alerts`), not wired — no execution paths exist yet to alert on. Wire when Stage 6 (real execution) lands. |

## GATED — v0.2, needs explicit greenlight per component (not a blanket unlock)

| Tool | Link | Gate condition |
|---|---|---|
| `market-intelligence` skill | (built in-house) | Reviewed, corrected, merged |
| `copy-trading` skill | (built in-house) | Corrected (5 changes), pending final commit |
| `regime-detection` skill | (built in-house) | Next in review sequence |
| `astra-analyst` skill | (built in-house) | Last in review sequence — extra scrutiny on prompt-injection surface before any commit |
| dexscreener-cli-mcp-tool | github.com/vibeforge1111/dexscreener-cli-mcp-tool | Skill proposed (`dexscreener-scan`), not built — held with rest of v0.2 |
| teamlore | npmjs.com/package/teamlore | Confirmed to be the legitimate small `.lore/` tool (zero deps, `teamlore@0.3.0`). Still not run — needs explicit go, and `DO_NOT_TRACK=1` must be set when it is |
| Firecrawl, TinyFish, BrowserUse | browser-use: github.com/browser-use/browser-use — Firecrawl/TinyFish: no verified repo link on file, env-var references only | `web-research-vetting` skill — gated to v0.2 wallet-vetting research only. Never for core price/execution data. Do not trigger on current momentum/cross-sectional-momentum work |
| OpenRouter | openrouter.ai | `openrouter` skill built for `astra-analyst`'s eventual LLM calls (verified `openai/gpt-6-astra` pricing live). Not called anywhere yet — `astra-analyst` isn't merged |

## EVALUATING — no decision yet, do not install pending review

| Tool | Link | What's being evaluated |
|---|---|---|
| cryptoskill registry | github.com/jiayaoqijia/cryptoskill | 977-skill community registry (includes Helius/Jupiter/DEXScreener skills). If ever needed, pull and read **individual named skills**, never bulk-install |
| immunity-agent (concept only) | github.com/PrismorSec/immunity-agent | Secret-cloaking concept is stronger than our current hook. **Do not use its "fetch a remote URL and follow its instructions" bootstrap under any circumstances** — that's a live prompt-injection vector regardless of vendor intent. If pursued, evaluate the actual source code directly and pin a specific commit |

## REJECTED — do not reconsider without re-reading the reasoning below

| Tool | Link | Why |
|---|---|---|
| ghostwright/phantom | github.com/ghostwright/phantom | Autonomous agent designed to act without asking permission, self-modifies its own config. Direct contradiction of this project's core posture |
| NoFxAiOS/nofx | github.com/NoFxAiOS/nofx | LLM decides trades directly, real exchange funds required. Opposite of `astra-analyst`'s "proposes, deterministic code disposes" design |
| kevinrgu/autoagent | github.com/kevinrgu/autoagent | Same autonomous self-modification pattern as phantom, applied to agent-harness R&D. Not relevant to TradeCC regardless |
| Esonhugh/tradingview | github.com/Esonhugh/tradingview | Needs your TradingView login persisted in a Chrome profile — a credential surface for indicators we already compute correctly |
| rohitg00/tailclaude | github.com/rohitg00/tailclaude | Exposes a full Claude Code control interface over Tailscale/public internet. Pure convenience, real attack-surface increase for a money-adjacent project |
| KeygraphHQ/shannon | github.com/KeygraphHQ/shannon | Autonomous pentester that executes real exploits. Wrong threat model — TradeCC has no web/API surface. Revisit only if a web dashboard is ever built, in full isolation from wallet/keys |
| `src/risk/fees.py` (pasted "Kimi" version) | (not a real repo — pasted code) | Collides with and would regress the real, calibrated fee model at that path |
| `validation_gate.py` (pasted "Kimi" version) | (not a real repo — pasted code) | Would create a second, JSON-file-based live-trading gate alongside the tested in-app one |
| pools.fun | pools.fun | Not a Solana product — SushiSwap v3 on Robinhood Chain |
| Starchild `official-skills` | github.com/Starchild-ai-agent/official-skills | Prompt/skill files, not runnable trading code; marginal value even for data ingestion |
| helicerat/geo-satellite-trader | (unverified) | Could not find or confirm this repository exists. Don't act on it without a working, verified link |

## PARKED — not relevant to current scope, no verdict needed

| Tool | Link | Why parked |
|---|---|---|
| SocratiCode | github.com/giancarloerra/SocratiCode | **Evaluated 2026-09-11 at v1.13.3, source read directly — sound tool, wrong scale.** Local-by-default confirmed (`EMBEDDING_PROVIDER \|\| "ollama"`; cloud needs both an explicit provider *and* a key, no telemetry). AGPL-3.0 genuine and no blocker for unmodified local use. Not adopted because the efficiency headroom is small: our whole repo is ~127k tokens (`src/*.py` ~74k, mean file ~1,090), and navigation already resolves in 1–3 grep/read calls — against a cost of Qdrant + Ollama containers and a ~270 MB model per session. Revisit if the repo passes ~500k tokens/thousands of files, or a large external corpus is vendored in. See `planning/architecture/socraticode-evaluation.md` |
| VinvAI | github.com/VinvAI/VinvAI | General Python testing/observability tool, unrelated to trading |
| pbakaus/impeccable, VoltAgent/awesome-design-md | github.com/pbakaus/impeccable | Frontend design skills — TradeCC is CLI-only, no UI in scope |
| V0DEV, Netlify | — | Dashboard/hosting tools; no UI greenlit yet |
| AI4Finance-Foundation/FinRL | github.com/AI4Finance-Foundation/FinRL | A genuinely different strategy class (reinforcement learning). Needs its own decision record if ever pursued, same as copy-trading did |
| docs.base.org custom-plugins | docs.base.org/agents/plugins/custom-plugins | Base/EVM-only; revisit for the eventual Base phase |
| DavidFeder/pulsechain-mcp | github.com/DavidFeder/pulsechain-mcp | PulseChain-only; revisit for the eventual PulseChain phase |
| Frankcastleauditor/safe-solana-builder | github.com/Frankcastleauditor/safe-solana-builder | Only relevant if we write a custom on-chain program, which nothing in the current plan requires |
| moondevonyt (moon-dev-ai-agents / -for-trading) | github.com/moondevonyt | Reference only, never run live — explicitly not profitable out of the box per its own README |
