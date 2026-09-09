# MVP Spec — v0.1: Solana Momentum Bot (Paper-Trading First)

## Overview
Build a Solana trading bot that trades a single momentum/TA strategy at
small position sizes, defaults to **paper trading** (simulated fills
against real market data, no real transactions), and can only be
switched to live trading once it clears an explicit validation gate.

## Goals
- A working, safe, observable v0.1 that can backtest, paper-trade, and
  (once validated) live-trade a momentum strategy on Solana at $5–$10
  position sizes.
- A codebase structured so copy-trading (v0.2) and additional chains
  (later phases) can be added without rewriting the execution or risk
  engine.
- Safety and cost-awareness built in from day one, not bolted on later.

## Non-goals (explicitly out of scope for v0.1)
- New-token sniping.
- Cross-DEX arbitrage.
- Base or PulseChain support.
- Copy-trading / wallet-following.
- A UI or dashboard — CLI/logs only for now.
- Managed-signing/KMS integration — env-var/secrets-manager key loading
  is sufficient for v0.1 (see `ops/CONTEXT.md`).

## Functional requirements
1. **RPC connectivity** — connect to Solana mainnet via Helius; fail
   loudly (not silently) if the RPC is unreachable or rate-limited.
2. **Price/OHLC data ingestion** — pull historical and near-real-time
   price data for a configurable token list (data source TBD — see open
   questions).
3. **Strategy signal generation** — a momentum module (EMA/RSI or
   similar) producing buy/sell/hold signals from the price data, with
   parameters exposed via config, not hardcoded.
4. **Three run modes, selected by explicit config/flag:**
   - `backtest` — run the strategy against historical data, no network
     calls to trade.
   - `paper` — run against live quotes, simulate fills and fees, log
     hypothetical trades, **send nothing to the network**. This is the
     default mode.
   - `live` — actually execute trades via Jupiter. Only runs if the
     validation gate below has been met; the code should refuse to run
     in `live` mode otherwise (not just discourage it — actually check
     and refuse).
5. **Execution (live mode only)** — get a Jupiter quote, run
   `simulateTransaction`, check the result against the configured
   slippage cap, and only then sign and send.
6. **Risk controls (enforced in code, all modes log what they *would*
   have done):**
   - Configurable position size, default $5–$10.
   - Per-trade stop-loss / take-profit.
   - Daily loss circuit breaker — halt trading for the day once a
     configured loss threshold is hit.
   - Slippage cap — reject a trade if effective slippage exceeds the
     configured threshold.
7. **Logging** — every signal, every simulated or real trade, and every
   risk-control trigger gets logged with enough detail to reconstruct
   what happened and why.
8. **Key handling** — wallet key loaded only from a secrets
   manager/env var at runtime; never written to logs, never committed.

## Non-functional requirements
- **Security:** see Non-negotiable rules in the top-level `CLAUDE.md` —
  they apply here without exception.
- **Reliability:** RPC calls need retry/backoff; a transient RPC failure
  should not be silently treated as "no signal."
- **Observability:** structured logs (not just print statements) so a
  human can audit a trading day after the fact.
- **Testability:** strategy logic and risk-control logic need unit
  tests independent of live network calls.
- **Cost-awareness:** respect Helius free-tier limits; don't poll faster
  than necessary.

## Validation gate (must pass before `live` mode is unlocked)
- Minimum 30 days of `paper` mode running against real market
  conditions.
- Strategy must show positive expectancy **after modeling realistic
  fees, slippage, and Jupiter's fee tiers** — not just gross P&L.
- Max drawdown during the paper period stays within a threshold the
  user sets before the test starts (define this in a decision record,
  not after the fact).
- Only after this passes: `live` mode unlocks, and even then starts at
  the $5–$10 default, not a larger size.

## Definition of done for v0.1
- `backtest` and `paper` modes run end-to-end against real Solana price
  data.
- Risk controls are unit-tested and demonstrably trigger (e.g., a test
  that forces a daily-loss breach and confirms trading halts).
- `live` mode exists in code but is gated behind the validation check
  and defaults to refusing to run.
- A README explains how to run each mode and what config each requires.

## Open questions (resolve before/while building — ask the user)
- Python or TypeScript? (Default assumption: Python — see
  `planning/decisions/2026-09-09-strategy-and-stack.md`.)
- OHLC/price data source for backtesting.
- Hosting target for `ops/deploy` (local vs. VPS).
- Helius tier ceiling (stay free vs. pay for Developer tier).
- Exact TA parameters (which EMA/RSI periods, which tokens to watch)
  and the max-drawdown threshold for the validation gate.
