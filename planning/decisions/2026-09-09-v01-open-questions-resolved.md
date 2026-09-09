# Decision: v0.1 Open Questions Resolved (2026-09-09)

## Context
`2026-09-09-strategy-and-stack.md` left four open questions for the user
and `specs/mvp_spec.md` listed the same set. All four are now answered.
This record confirms (does not supersede) that earlier decision record —
strategy, chain, scope, and swap/routing are unchanged.

## What we decided

**Language: Python.** Confirms the earlier assumption rather than
overriding it. The reasoning was re-examined against TypeScript before
confirming:

- v0.1 is gated on a *backtest*, and Python's backtesting/indicator
  ecosystem (`pandas`, `pandas-ta`, `vectorbt`/`backtesting.py`) is
  substantially more mature than TypeScript's. That tooling covers the
  part of the system that decides whether the strategy is real or
  curve-fit.
- The counter-argument for TypeScript is SDK quality (`@solana/web3.js`
  / Kit are first-class, and Jupiter's own examples are TS-first). But
  the network surface here is small: Jupiter quote and swap are plain
  HTTP in either language, and the only genuinely SDK-dependent step is
  sign/simulate/send, which `solders` handles cleanly.
- Net: TypeScript would improve a small fraction of the codebase and
  weaken the validation layer. Revisit only if v0.2 copy-trading turns
  into a latency-sensitive problem.

**OHLC/price data source: GeckoTerminal.** Free, no API key, OHLCV for
Solana DEX pools including long-tail tokens, ~30 req/min. Adequate for
EMA/RSI on 5m–1h candles. Candles are cached to disk so backtests are
reproducible and runnable offline.

- Fallback if rate limits or data gaps actually bite: **Birdeye** (paid
  tier). Do not switch pre-emptively — switch on evidence, and record it
  as a new decision.
- Rejected: CoinGecko (misses most long-tail Solana pairs);
  self-recorded Jupiter candles as the *primary* source (no history on
  day one, which blocks backtesting entirely).
- The data source is behind an interface in `src/` so swapping it does
  not touch strategy or risk code.

**Hosting: local now, small VPS for the paper run.** Develop and
backtest locally; deploy to a ~$5/mo VPS for the continuous 30-day paper
validation run. Rationale: the validation gate requires 30 days against
real market conditions, and a laptop that sleeps or reboots leaves gaps
that weaken the gate.

**Helius tier: free.** Candles come from GeckoTerminal, so RPC is only
needed for `simulateTransaction`, send, and balance checks — comfortably
within free limits. Upgrade to Developer (~$49/mo) only if rate limits
are actually hit, and record it when it happens.

## Consequences
- `specs/mvp_spec.md` open-questions list is now reduced to the two
  parameter questions below.
- `ops/deploy` targets a small Linux VPS; deployment work is not needed
  until the paper run starts, but key handling on that host must follow
  the pattern in `ops/CONTEXT.md`.
- Polling cadence must respect ~30 req/min on GeckoTerminal and stay
  inside Helius free-tier limits — build rate limiting in, don't
  discover it in production.

## Still open — must be resolved before the paper run starts
- **Exact TA parameters** (EMA/RSI periods) and the **token watchlist**.
  Defaults will be proposed in config and validated by backtest; they
  are config values, not code constants, so they do not block
  scaffolding.
- **Max-drawdown threshold for the validation gate.** Per
  `specs/mvp_spec.md` this must be set in a decision record *before* the
  30-day paper clock starts — a threshold chosen afterwards is not a
  gate. This is a blocker for starting the paper run, not for building.
