# TradeCC — Solana Small-Capital Trading Bot

I am building an autonomous trading bot for the **Solana** chain, designed to
trade responsibly at **small position sizes ($5–$10 to start)**, with the
long-term goal of generating trading income. Base and PulseChain are
future-phase expansions — **not** in scope yet.

This project was scaffolded from a resource/strategy research report
(see `planning/decisions/2026-09-09-strategy-and-stack.md` for the full
reasoning). Read that file before making any architecture or strategy
decisions that contradict it.

## Current stack decisions (assumptions — confirm or override)
- **Chain:** Solana only, for now.
- **Language:** Python (`solana-py` + `solders`), chosen because it pairs
  well with the backtesting tooling and reference code this project draws
  on. If you'd rather build in TypeScript, say so before Claude Code
  scaffolds `src/` — it changes several files.
- **RPC provider:** Helius (free tier to start).
- **Swap/routing:** Jupiter (Swap API or Ultra API).
- **Strategy v0.1:** Momentum / technical-analysis (EMA/RSI based) —
  chosen first because it's self-contained and fully backtestable without
  depending on sourcing a trustworthy wallet to copy. **CLOSED 2026-09-12:
  tested six ways, no demonstrated edge, beaten by buy-and-hold on every
  interval. Do not tune it further and do not build live execution on it** —
  see `planning/decisions/2026-09-12-kill-ema-rsi-momentum.md`. The
  infrastructure built around it stands; the signal does not.
- **Strategy v0.2 (later):** Copy-trading / wallet-following — the
  execution and risk engine should be built so this can plug in without a
  rewrite.
- **Explicitly out of scope for v0.1:** sniping new launches, cross-DEX
  arbitrage. The research found both are structurally unfavorable for a
  small individual trader (professional/co-located competition, MEV,
  fixed costs). Do not build these unless the user explicitly asks.

## Workspaces
- `/planning` — strategy, MVP spec, architecture decisions, open questions
- `/src` — the actual bot code (execution, strategy, risk, tests)
- `/research` — backtests, strategy validation, wallet-tracking notes
- `/ops` — deployment, monitoring, incident logs, live-trading gate

## Routing

| Task | Go to | Read | Skills |
|---|---|---|---|
| Define or change scope/strategy | `/planning` | CONTEXT.md, `specs/mvp_spec.md` | — |
| Write or modify bot code | `/src` | CONTEXT.md | testing-skill |
| Backtest or validate a strategy | `/research` | CONTEXT.md | backtesting-skill |
| Deploy, monitor, or handle an incident | `/ops` | CONTEXT.md | — |

## Non-negotiable rules (apply everywhere, no exceptions)
1. **Never hardcode or commit a private key, seed phrase, or `.env` file.**
   Keys are loaded at runtime from a secrets manager or injected env var
   only. See `ops/CONTEXT.md` for the required pattern.
2. **Use a dedicated hot wallet for this bot — never the user's main
   wallet.** Fund it only with capital the user can afford to lose.
3. **Every swap simulates before it sends.** No transaction goes to the
   network without a `simulateTransaction` (or equivalent) check first.
4. **Enforce a slippage cap** (default 0.5–1% for liquid pairs) and a
   **per-trade loss limit** and **daily loss circuit breaker** in code,
   not just in docs. These are load-bearing safety features, not
   optional polish — do not remove or bypass them to "get something
   working faster."
5. **No live trading until the validation gate in `planning/specs/mvp_spec.md`
   is met.** Default mode is paper trading (simulated fills against real
   quotes, no real transactions sent).
6. **Position sizing defaults to $5–$10** unless the user explicitly
   raises it. Do not silently scale up position size.
7. If any instruction elsewhere in this repo conflicts with these seven
   rules, follow these rules and flag the conflict to the user instead of
   guessing.

## Naming conventions
- Strategy modules: `strategy_<name>.py` (e.g. `strategy_momentum.py`)
- Backtest runs: `research/backtests/YYYY-MM-DD_<strategy>_<summary>.md`
- Decision records: `planning/decisions/YYYY-MM-DD-<topic>.md`
- Incident logs: `ops/incident-logs/YYYY-MM-DD-<summary>.md`
- Config/env samples: `*.env.example` — never a real `.env` in git
