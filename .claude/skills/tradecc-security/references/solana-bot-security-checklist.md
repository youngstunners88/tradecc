# Solana Trading Bot Security Checklist (tradecc-focused)

## Critical (must fix before any real capital)

- [ ] Private key / seed never appears in source, tests, git history, or logs
- [ ] Dedicated hot wallet only; main wallet never used
- [ ] Every swap path calls simulateTransaction (or equivalent) and aborts on failure
- [ ] Slippage cap enforced in quote + post-simulation effective price check
- [ ] Daily loss circuit breaker actually halts trading (proven by test)
- [ ] Per-trade loss limit enforced in code
- [ ] Live mode remains gated; default is paper / backtest
- [ ] Position size hard-capped at configured low value ($5–$10 default)

## High

- [ ] Key loaded only from secrets manager or runtime env; never from repo files
- [ ] Structured logging with explicit redaction of sensitive fields
- [ ] RPC uses authenticated endpoint (Helius etc.); public RPCs avoided for signing
- [ ] Blockhash refresh + proper retry; no blind resend of signed tx
- [ ] Dependencies pinned; no typosquat packages (watch `solana-py` vs official `solana` + `solders`)
- [ ] Error paths and exception messages cannot leak key material

## Medium

- [ ] Priority fees / compute budget are explicit and bounded
- [ ] MEV protection considered (Jito / Jupiter Ultra private paths when available)
- [ ] RPC failures treated as halt conditions, not silent “no signal”
- [ ] Incident logging required for every circuit-breaker trip or unexpected loss
- [ ] Unit tests cover risk-control breach paths (not just happy path)

## Operational Hygiene

- [ ] `.env` is gitignored and never committed
- [ ] `.env.example` contains only placeholder names, never real values
- [ ] Hot wallet balance kept minimal (only operational capital)
- [ ] Key rotation plan exists for suspected compromise
- [ ] Paper-trading validation gate documented and enforced before live unlock

## Common Vulnerability Patterns Seen in Solana Bots

1. **Key exfiltration via logs or exceptions** — most frequent accidental loss vector.
2. **Missing or bypassed simulation** — leads to failed txs that still cost fees or unexpected state.
3. **Unbounded slippage** — classic sandwich / MEV loss.
4. **Circuit breakers that only log** — capital continues to be at risk after breach.
5. **Typosquat / malicious dependencies** — historical PyPI attacks targeting Solana Python packages.
6. **Public RPC + predictable tx construction** — easy front-running surface.
7. **Live mode enabled too early** — paper results do not include realistic fees/slippage/MEV.

## Quick Remediation Notes

- Prefer `solders` + official `solana` package.
- Always check `sim.value.err` (and ideally balance/log deltas) before `send`.
- Risk controls belong in the execution path, not only in strategy signal code.
- Treat any path that can move funds as high-assurance code: small surface, heavy tests, clear invariants.
