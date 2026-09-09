# Src — CONTEXT.md

## What happens here
This is the actual bot codebase. Everything here should trace back to a
requirement in `planning/specs/mvp_spec.md`. If you're about to write
code that isn't in the spec, stop and check whether the spec needs
updating first (that's a `/planning` task).

## Structure
- `core/` — config loading and validation, domain types, structured
  logging with redaction, telemetry, rate limiting, and the live-trading
  gate. No trading logic; everything else depends on it.
- `execution/` — RPC client (Helius), Jupiter quote/swap calls,
  market data (GeckoTerminal), candle caching, `simulateTransaction`
  wrapper, transaction signing/sending. This is the ONLY place that
  talks to the network or touches the wallet key. Market data lives here
  for exactly that reason, even though it does not trade.
- `backtest/` — the backtest run mode: the bar-by-bar runner and the
  report writer. Depends on strategy, risk, and execution; nothing
  depends on it.
- `strategy/` — strategy modules. v0.1 has one: momentum/TA
  (`strategy_momentum.py`). Must be pluggable — a future
  `strategy_copytrade.py` (v0.2) should be able to drop in against the
  same interface without changes to `execution/` or `risk/`.
- `risk/` — position sizing, slippage cap enforcement, stop-loss/
  take-profit, daily loss circuit breaker. This module has veto power:
  `execution/` must check with `risk/` before sending any trade, in
  every mode.
- `tests/` — unit tests. Strategy and risk logic must be testable
  without live network calls (mock the RPC/Jupiter responses).

## Libraries (per the stack decision in `planning/decisions/`)
- Solana RPC: `solana-py` + `solders`
- Swap/routing: Jupiter Swap API or Ultra API (HTTP calls; no special
  SDK required, but check for an official Python client first)
- Config: environment variables + a config file for strategy parameters
  (not hardcoded constants)

## Non-negotiable rules for this workspace (restated from CLAUDE.md — do not skip)
- No private key, seed phrase, or `.env` file ever committed. Keys load
  from env var / secrets manager at runtime only.
- Every live trade simulates before it sends — no exceptions, no
  "just for testing" bypasses left in the code path that live mode uses.
- `risk/` checks (slippage cap, position size, stop-loss, daily circuit
  breaker) are enforced in code and unit-tested — not just documented.
- `live` mode must actually check the validation gate from the spec and
  refuse to run if it hasn't been met. Don't stub this as a TODO and
  leave live mode open.
- Position size defaults to $5–$10; don't hardcode a larger default
  "to make testing easier" — use a clearly-separate backtest/paper
  config for that instead.

## Naming conventions
- Strategy modules: `strategy_<name>.py`
- Test files: `test_<module>.py`
- Config files: `config.<mode>.yaml` or `.env.example` (never a real
  `.env`)

## Testing requirements
- Every strategy module needs unit tests covering signal generation on
  known input data.
- Every risk-control function needs a test that proves it actually
  blocks/halts trading when its threshold is breached — not just that it
  logs a warning.
- Execution code should be tested against mocked RPC/Jupiter responses;
  do not require a live network connection for the test suite to pass.
