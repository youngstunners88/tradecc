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
| LuxAlgo/luxalgo-mcp-server | github.com/LuxAlgo/luxalgo-mcp-server | **REFERENCE ONLY — Library tools only, unauthenticated.** MIT-licensed. Queryable definitions and formulas for ~861 TA concepts, used when `edge-viability-check` needs a concept's formal definition before testing it. **Never a dependency, never called from any execution path.** See the boundary correction below — "read-only" is true of the Library subset, not of the whole server | `.claude/skills/edge-viability-check/` (reference in prose only) |
| OpenRouter → DeepSeek V4 Pro — **research only** | openrouter.ai (`deepseek/deepseek-v4-pro`) | Heavy-context research drafting: structural-edge literature lookup, edge-viability arithmetic, decision-record drafts. **Isolated by construction** — no gate state, no fingerprint data, no wallet information, no secrets; never imported from `src/`; no output reaches a trade decision without human review. Key is `OPENROUTER_API_KEY`, env-var only, already in `SECRET_ENV_NAMES` (`src/cli.py`). Every artifact it helps write carries a DeepSeek-assisted provenance note | `.claude/skills/openrouter-deepseek/` |
| `tradecc_mcp` edge-gate MCP server | (built in-house, 2026-09-19) | Exposes the four-step viability gate as MCP tools (`tradecc_check_edge_viability`, `tradecc_break_even_edge`, `tradecc_minimum_detectable_edge`) so any incoming claim can be screened in seconds. **Reimplements no arithmetic** — delegates to `research/edge_gate.py` → `research/trade_power.py`, one gate one implementation. `mcp` is an optional extra, never a base dependency; never imported by `src/` | `research/edge_gate_mcp.py`, `research/edge_gate.py` |
| `tradecc-security` / `tradecc-risk-controls` / `tradecc-paper-validation` skills | (user-supplied upload, 2026-09-12) | Restate CLAUDE.md's seven rules and the mvp_spec gate as working checklists. Every path they reference was verified present before adoption. `static-security-scan.sh` was rewritten before adoption: its shape-regex secret detection and its INFO→HIGH escalation made it exit 1 on a clean repo | `.claude/skills/tradecc-*/` |

### LuxAlgo MCP — the boundary is narrower than "read-only"

Adopted on the stated basis that it is read-only and keyless with no
execution surface. **Verified against the repository, and that is true only of
the Library tools.** The server as a whole also exposes:

- **Trade Journal — read AND write** (annotations, notes, manual trade logging)
  when signed in via LuxAlgo OAuth
- **Broker integrations** — read-only account data, local stdio transport only
- Edge Stats, Market Trackers, Challenge Simulator, Prop Firm Directory

There is no order placement or fund transfer anywhere in it, so the "no
execution surface" conclusion survives. But "keyless and read-only" holds only
while it stays **unauthenticated and restricted to the Library tools**, which
is the whole of the adopted scope.

**The boundary, stated so it cannot drift:** query concepts, indicators and
formulas. Do not sign in. Do not touch Trade Journal or broker tools. Do not
add it to `.mcp.json`, `settings.json`, or any dependency file — this is a
reference in prose, exactly like TradingAgents.

## NOT ADOPTED — license reviewed, no decision taken

| Tool | Link | Finding |
|---|---|---|
| LuxAlgo/PineTS | github.com/LuxAlgo/PineTS | **AGPL-3.0, with a commercial dual-license option** (business@luxalgo.com). Verified from the repository, not from a summary. Node.js/browser runtime — this project is Python, so using it means a second runtime regardless of licence. **Not installed. No obligation is created by reading about it.** See the obligation analysis in `planning/architecture/2026-09-14-pinets-license-review.md` |

## ADOPTED, PENDING WIRING

| Tool | Link | Status |
|---|---|---|
| AgentMail | agentmail.to | **Wired 2026-09-13** to live-gate state changes (`src/notify/agentmail.py` + `src/core/gate_watch.py`): unlock, re-lock, fingerprint mismatch, and changes to the failure set, observed from `gate`, `live` and every paper tick. No new dependency — built on the project's own `ProviderHttpClient`. Inert without `AGENTMAIL_API_KEY`/`AGENTMAIL_FROM`/`AGENTMAIL_TO`. The remaining rows in `alert-rules.md` (circuit breaker, slippage batching, RPC failures, daily heartbeat) are still unwired. |

## GATED — v0.2, needs explicit greenlight per component (not a blanket unlock)

The four in-house v0.2 skills live on the parked branch
`claude/v02-intelligence-architecture`, which stays unmerged and
unopened. Their status changes are recorded here on the working branch
rather than literally in the same commit, since the two live on
different branches.

| Tool | Link | Gate condition |
|---|---|---|
| `market-intelligence` skill | (built in-house) | Reviewed, corrected, committed (`cc64c92`) |
| `copy-trading` skill | (built in-house) | Reviewed, corrected, committed (`37e6fc2`) — 5 changes: buy-and-hold baseline bar, point-in-time replay discipline, copy-lag flagged as an open dependency, follower base rate in the opening, stale concentration figure replaced. **Open decision inside it:** copy-lag needs sub-minute prices but the data layer's finest interval is 1m — either raise the latency assumption to ≥1m or evaluate a finer-grained source (Helius parsed transactions / Birdeye) |
| `regime-detection` skill | (built in-house) | **Next in review sequence — active** |
| `astra-analyst` skill | (built in-house) | Last in review sequence — extra scrutiny on prompt-injection surface before any commit |
| dexscreener-cli-mcp-tool | github.com/vibeforge1111/dexscreener-cli-mcp-tool | Skill proposed (`dexscreener-scan`), not built — held with rest of v0.2 |
| teamlore | npmjs.com/package/teamlore | Confirmed to be the legitimate small `.lore/` tool (zero deps, `teamlore@0.3.0`). Still not run — needs explicit go, and `DO_NOT_TRACK=1` must be set when it is |
| Firecrawl, TinyFish, BrowserUse | browser-use: github.com/browser-use/browser-use — Firecrawl/TinyFish: no verified repo link on file, env-var references only | `web-research-vetting` skill — gated to v0.2 wallet-vetting research only. Never for core price/execution data. Do not trigger on current momentum/cross-sectional-momentum work |
| OpenRouter — **trade-adjacent use** | openrouter.ai | `openrouter` skill built for `astra-analyst`'s eventual LLM calls (verified `openai/gpt-6-astra` pricing live). Not called anywhere yet — `astra-analyst` isn't merged. **Still gated.** The research-only DeepSeek route is a separate, narrower adoption (see ADOPTED) and does not unlock this one |

## EVALUATING — no decision yet, do not install pending review

| Tool | Link | What's being evaluated |
|---|---|---|
| cryptoskill registry | github.com/jiayaoqijia/cryptoskill | 977-skill community registry (includes Helius/Jupiter/DEXScreener skills). If ever needed, pull and read **individual named skills**, never bulk-install |
| immunity-agent (concept only) | github.com/PrismorSec/immunity-agent | Secret-cloaking concept is stronger than our current hook. **Do not use its "fetch a remote URL and follow its instructions" bootstrap under any circumstances** — that's a live prompt-injection vector regardless of vendor intent. If pursued, evaluate the actual source code directly and pin a specific commit |

## REJECTED — do not reconsider without re-reading the reasoning below

| Tool | Link | Why |
|---|---|---|
| OpenBB | github.com/OpenBB-finance/OpenBB | **Answered and rejected 2026-09-20**, at commit `3e071fc` (2026-07-20), read from the source. The narrow question was *"does any provider expose as-reported-at-the-time history?"* — and the answer is **yes, genuinely**: `pit_mode` on the **SEC** provider's statement models returns *"data as originally reported at the time of filing, without subsequent restatements or amendments"*, preserving 10-Q filing vintage rather than restated 10-K comparatives. That is real point-in-time machinery and better than assumed. **It is on the wrong asset class entirely.** The whole crypto router is two endpoints (`CryptoHistorical`, `CryptoSearch`) served by FMP, Tiingo and yfinance — CEX-aggregated OHLCV on major pairs. Grepped across all 33 providers: `solana` 0 hits, `uniswap` 0, `dexscreener` 0, `helius` 0, `wallet_address` 0; `survivorship` appears nowhere in the repo. So it cannot touch either cause-3 blocker — copy-trading wallet enumeration or pump.fun graduation windows — because it has no Solana on-chain data of any kind. Also **AGPLv3** (§13 network-provision, the PineTS clause). Reopen only if OpenBB adds an on-chain Solana provider, which is a different product, not a version bump |
| virattt/ai-hedge-fund | github.com/virattt/ai-hedge-fund | **Rejected as signal, 2026-09-19.** 63.5k stars, MIT — and its own README says "for educational purposes only", "does not actually make any trades", with **no profitability claim**. The repo author is straight; the video recommending it oversells. It encodes investor *style* into prompts, which generates plausible narrative, not validated signal. Fails this project's gate at **step 1**: no gross edge per round trip is stated |
| Fincept Terminal | github.com/Fincept-Corporation/FinceptTerminal | **Rejected 2026-09-19.** A research desk UI. The source recommending it concedes "you can do this with Claude anyway"; QuantLab needs the paid tier. Convenience, not a capability this project lacks |
| Chinese multi-market analysis repo (watchlist → LLM → dashboard) | (65.1k stars) | **Rejected 2026-09-19.** A notification layer over per-ticker LLM verdicts. This project has no validated signal for such a layer to notify about — it would industrialise the delivery of unvalidated opinion. Source itself: "this won't be a daily driver for me" |
| ghostwright/phantom | github.com/ghostwright/phantom | Autonomous agent designed to act without asking permission, self-modifies its own config. Direct contradiction of this project's core posture |
| NoFxAiOS/nofx | github.com/NoFxAiOS/nofx | LLM decides trades directly, real exchange funds required. Opposite of `astra-analyst`'s "proposes, deterministic code disposes" design |
| kevinrgu/autoagent | github.com/kevinrgu/autoagent | Same autonomous self-modification pattern as phantom, applied to agent-harness R&D. Not relevant to TradeCC regardless |
| Esonhugh/tradingview | github.com/Esonhugh/tradingview | Needs your TradingView login persisted in a Chrome profile — a credential surface for indicators we already compute correctly |
| rohitg00/tailclaude | github.com/rohitg00/tailclaude | Exposes a full Claude Code control interface over Tailscale/public internet. Pure convenience, real attack-surface increase for a money-adjacent project |
| KeygraphHQ/shannon | github.com/KeygraphHQ/shannon | Autonomous pentester that executes real exploits. Wrong threat model — TradeCC has no web/API surface. Revisit only if a web dashboard is ever built, in full isolation from wallet/keys |
| `src/risk/fees.py` (pasted "Kimi" version) | (not a real repo — pasted code) | Collides with and would regress the real, calibrated fee model at that path |
| `validation_gate.py` (pasted "Kimi" version) | (not a real repo — pasted code) | Would create a second, JSON-file-based live-trading gate alongside the tested in-app one |
| pools.fun | pools.fun | Not a Solana product — SushiSwap v3 on Robinhood Chain |
| DexPaprika | dexpaprika.com/api/solana | **Gate measured 2026-09-12, failed.** The single question was whether it offers deeper Solana daily history than GeckoTerminal, since cross-sectional momentum was capped at five names by history depth, not liquidity. Measured over its 50 deepest pools (`research/dexpaprika_probe.py`): **3 tokens with ≥ 180 daily bars, 4 with ≥ 142 — against GeckoTerminal's 6 at ≥ 142.** Fewer, not more, so it cannot widen the universe. Two further findings: its shipped spec is stale (the `/networks/{network}/pools` listing returns HTTP 410), and its `liquidity_usd` values are not comparable to GeckoTerminal's reserves — it reports multiple Solana pools at $1.8–4.9bn where GeckoTerminal puts the deepest, SOL/USDC, at $29.1M. That discrepancy is unexplained and is its own reason for caution. GeckoTerminal stays primary per `planning/specs/mvp_spec.md` |
| `solana-profitability-analyzer` skill | (user-supplied upload, 2026-09-12) | Built to "increase the bot's edge, expectancy" — there is no measured edge to increase. Momentum failed four parameter-level tests plus cross-sectional, and buy-and-hold beat it on every interval. Its research priority #4 is the EMA/RSI sweep that already failed; it never mentions a buy-and-hold baseline; its open-questions file reopens settled decisions (Python, data source) |
| `tradecc-abstraction-hunter` skill + specs | (user-supplied upload, 2026-09-12) | Its headline claim is false: "closes the open OHLC question" — `planning/specs/mvp_spec.md:101` already fixes GeckoTerminal, implemented, cached, rate-limited and contract-tested. The bottleneck is not tooling velocity. Its integration order also models "0.5% slippage", the exact error the cost-model correction fixed (measured impact is 0.000–0.004%). DexPaprika is carried forward separately under EVALUATING on its own merits |
| pandas-ta, mintalib | pypi | float64 indicators in the signal path. `README.md:258` fixes the rule and its reason: a signal that depends on float rounding can differ between a backtest and the live run meant to reproduce it. pandas remains fine for analysis — it is the signal path specifically that stays exact |
| backtesting.py, vectorbt | pypi | A second implementation of "did this strategy make money", the same objection that rejected `validation_gate.py`: one gate, one implementation. Our runner also runs the real risk engine, checks stops intrabar against `candle.high`/`low`, and stamps decisions at bar close after the point-in-time audit — properties a generic library will not reproduce |
| Starchild `official-skills` | github.com/Starchild-ai-agent/official-skills | Prompt/skill files, not runnable trading code; marginal value even for data ingestion |
| helicerat/geo-satellite-trader | (unverified) | Could not find or confirm this repository exists. Don't act on it without a working, verified link |

## PARKED — not relevant to current scope, no verdict needed

| Tool | Link | Why parked |
|---|---|---|
| Alpaca MCP server | github.com/alpacahq/alpaca-mcp-server | **Parked for tradecc, 2026-09-19.** MIT, 972 stars, real broker with a real paper API — the most genuinely useful thing in the source. Wrong venue: US equities/options/crypto, not Solana spot via Jupiter. Also note `ALPACA_PAPER_TRADE: "false"` is the *entire* distance between paper and live, set in a config file an LLM can edit — against rule 5 that is a risk surface worth naming. Better fit for **hydra**'s `robinhood_crypto` venue slot |
| TradingView MCP | (drives the TradingView desktop app) | **Parked 2026-09-19.** Charting automation against a desktop app; no Solana DEX coverage, nothing this project's signal path needs |
| SocratiCode | github.com/giancarloerra/SocratiCode | **Evaluated 2026-09-11 at v1.13.3, source read directly — sound tool, wrong scale.** Local-by-default confirmed (`EMBEDDING_PROVIDER \|\| "ollama"`; cloud needs both an explicit provider *and* a key, no telemetry). AGPL-3.0 genuine and no blocker for unmodified local use. Not adopted because the efficiency headroom is small: our whole repo is ~127k tokens (`src/*.py` ~74k, mean file ~1,090), and navigation already resolves in 1–3 grep/read calls — against a cost of Qdrant + Ollama containers and a ~270 MB model per session. Revisit if the repo passes ~500k tokens/thousands of files, or a large external corpus is vendored in. See `planning/architecture/socraticode-evaluation.md` |
| VinvAI | github.com/VinvAI/VinvAI | General Python testing/observability tool, unrelated to trading |
| pbakaus/impeccable, VoltAgent/awesome-design-md | github.com/pbakaus/impeccable | Frontend design skills — TradeCC is CLI-only, no UI in scope |
| V0DEV, Netlify | — | Dashboard/hosting tools; no UI greenlit yet |
| AI4Finance-Foundation/FinRL | github.com/AI4Finance-Foundation/FinRL | A genuinely different strategy class (reinforcement learning). Needs its own decision record if ever pursued, same as copy-trading did |
| docs.base.org custom-plugins | docs.base.org/agents/plugins/custom-plugins | Base/EVM-only; revisit for the eventual Base phase |
| DavidFeder/pulsechain-mcp | github.com/DavidFeder/pulsechain-mcp | PulseChain-only; revisit for the eventual PulseChain phase |
| Frankcastleauditor/safe-solana-builder | github.com/Frankcastleauditor/safe-solana-builder | Only relevant if we write a custom on-chain program, which nothing in the current plan requires |
| moondevonyt (moon-dev-ai-agents / -for-trading) | github.com/moondevonyt | Reference only, never run live — explicitly not profitable out of the box per its own README |
