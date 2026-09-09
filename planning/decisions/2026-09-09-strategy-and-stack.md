# Decision: Strategy & Stack for v0.1 (2026-09-09)

## Context
A research pass evaluated six candidate resources and the general Solana
small-capital trading landscape. Full report retained separately by the
user; this file captures the decisions that follow from it, for Claude
Code to treat as ground truth.

## What we decided

**Chain:** Solana first. Base and PulseChain are deferred.

**Strategy for v0.1:** Momentum / TA-based trading (EMA/RSI style
signals). Rationale: at $5–$10 position sizes, only copy-trading and
momentum/TA are viable — sniping and arbitrage are dominated by
professional, co-located, low-latency operators and are structurally
unfavorable for a small retail trader. Momentum/TA was picked to go
first (over copy-trading) because it's fully backtestable and doesn't
depend on first solving "which wallet do we trust enough to copy."

**Strategy for v0.2 (later, not now):** Copy-trading / wallet-following.
The execution and risk engine must be strategy-agnostic so this can be
added without rewriting `src/execution` or `src/risk`.

**RPC provider:** Helius, free tier to start (upgrade to Developer
~$49/mo only if rate limits are actually hit).

**Swap/routing:** Jupiter (Swap API or Ultra API) — the standard Solana
DEX aggregator, returns a ready-to-sign transaction with routing already
solved.

**Language:** Python (`solana-py` + `solders`) — assumption, not a hard
requirement. Flag to the user before scaffolding if TypeScript is
preferred.

**Wallet/key management:** Dedicated hot wallet, key never committed,
loaded at runtime from a secrets manager or injected env var. Managed
signing/KMS is a later upgrade once capital grows.

## Resources evaluated — what to actually use

| Resource | Verdict | Use for |
|---|---|---|
| Moon Dev GitHub (`moon-dev-ai-agents`) | Keep — reference only | Python patterns, Jupiter execution snippets, RBI backtest pattern. Explicitly **not profitable out of the box** per its own README — do not run live as-is. |
| `soltrade` (nmweaver) | Keep — reference | Minimal Python TA (EMA/RSI/Bollinger) + Jupiter integration reference for the v0.1 strategy module. |
| `outsmart-cli` / `solana-trading-cli` (outsmartchad) | Keep — reference | Most complete open execution toolkit (18 DEX adapters, Jupiter/DFlow, Jito/Helius Sender landing) if we need execution patterns beyond plain Jupiter calls. |
| `warp-id/solana-trading-bot` | Reference only | Sniper-focused; useful for TP/SL and filter patterns, not for v0.1 since sniping is out of scope. |
| `safe-solana-builder` (Frankcastleauditor) | Discard for now | Only relevant if we later write a custom on-chain program (e.g. an arbitrage contract). v0.1 only calls Jupiter — no on-chain program of our own. |
| `pulsechain-mcp` (DavidFeder) | Discard for now | PulseChain only; revisit if/when PulseChain phase starts. Also immature (1 commit, 1 star) — audit before funding if reused later. |
| `docs.base.org` custom-plugins | Discard for now | Base/EVM only; revisit for Base phase. The read → prepare(unsigned tx) → sign/send separation is a good pattern to reuse architecturally when we get there. |
| Starchild `official-skills` | Discard | AI-agent prompt/skill files, not runnable trading code. Marginal value even for data ingestion. |
| pools.fun | Discard entirely | Not a Solana product — it's a SushiSwap v3 front-end on Robinhood Chain. |

## Cost/risk facts that shape the spec
- Fixed costs (base fee, priority fee, Jito tip, ~0.002 SOL ATA rent per
  new token, Jupiter's tiered fee, slippage) are the dominant risk at
  $5–$10 sizes — they don't scale down, so small trades bear a
  disproportionate cost. This is why the risk module and slippage caps
  in `src/risk` are mandatory, not optional.
- Sandwich/MEV attacks are a real, quantified risk on Solana despite no
  public mempool by default. Tight slippage + Jupiter's MEV-protect/Jito
  routing + `simulateTransaction` are the mitigations — build them in
  from day one.
- Copy-trading platforms carry counterparty risk (a documented 2026
  case of an exchange insider front-running copy-traders). This is
  another reason v0.1 avoids depending on a third-party copy-trading
  platform and, if v0.2 copy-trading is built, it should be self-hosted
  wallet-following, not a hosted platform integration.

## Open questions for the user
- Confirm Python vs. TypeScript.
- Which OHLC/price data source for backtesting (Birdeye? Jupiter price
  API? something else)?
- Where will the bot run (local machine vs. a small VPS)? Affects
  `ops/deploy`.
- Budget ceiling for Helius (stay on free tier vs. Developer tier)?
