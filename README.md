# TradeCC

Autonomous momentum trading bot for **Solana**, built to trade at small
position sizes ($5–$10) and default to **paper trading** until it clears an
explicit validation gate.

Read `CLAUDE.md` first — it holds the seven non-negotiable safety rules.
`planning/specs/mvp_spec.md` defines what v0.1 is.

## Status: Stage 1 of 7

This is **not a runnable bot yet.** What exists is the foundation and the
safety layer that everything else gets built against, deliberately built
before any code that can touch the network or a wallet.

| Stage | Scope | State |
|---|---|---|
| 0 | Config, domain types, structured logging, live gate | ✅ Done |
| 1 | Risk engine: sizing, slippage, stops, circuit breaker | ✅ Done |
| — | CI (tests + coverage floor), PostHog telemetry | ✅ Done |
| 2 | Execution layer: mock, fill simulator, Helius + Jupiter (read-only) | ✅ Done |
| 3 | Momentum strategy module | ✅ Done |
| 4 | Backtest mode (GeckoTerminal data, net-of-fees reporting) | ✅ Done |
| 5 | Paper mode wiring | ⬜ Next |
| 6 | Live execution, gated | ⬜ |
| 7 | Ops, monitoring, deploy | ⬜ |

There is currently **no CLI entrypoint and no wallet handling.** The
execution layer is read-only: it fetches quotes and RPC state, and there
is no code path that builds, signs, or sends a transaction. Both client
classes have a test asserting their public surface, so adding a `send`
method fails the suite rather than slipping in quietly.

## The execution seam

`execution/` is the only package that talks to the network. The mocking
boundary is the **HTTP transport**, not the client:

- **Unit tests never touch the network** — not "shouldn't", *can't*. The
  transport is injected, tests pass a fake returning canned payloads, and
  there is no ambient client able to make a real request.
- Retry, backoff, `Retry-After` handling, rate limiting, and error mapping
  are all covered by those offline tests. Mocking at the client level
  would leave exactly that logic untested.
- `MockQuoteSource` is the separate seam for exercising strategy and risk
  end-to-end offline. A test asserts it and the real Jupiter client are
  substitutable through the same `QuoteSource` protocol.

### Simulated fills are pessimistic on purpose

Paper and backtest fills use the quote's **worst-case** price, never its
expected price, and cost modelling defaults are deliberately harsh. An
optimistic simulation produces a validation gate that passes systems which
then lose money live — the most expensive failure mode this project has.

The cost model makes the small-size problem visible: on a $5 position that
opens a new token account, fixed costs exceed **8% of the position** before
the price moves at all.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Copy `.env.example` to `.env` for local development. `.env` is gitignored
and must never be committed.

## Run modes

Selected by `BOT_MODE`, or the `mode:` key in the config file, or an
explicit argument — resolved in that order of precedence. There is no
default; an unset mode is an error rather than a guess.

| Mode | Config | Network | Sends transactions |
|---|---|---|---|
| `backtest` | `config.backtest.yaml` | Historical data only | No |
| `paper` | `config.paper.yaml` | Real quotes | **No** — simulated fills |
| `live` | `config.live.yaml` | Real quotes | Yes — **gated** |

## The live gate

`live` mode is locked, and setting `mode: live` does not unlock it. The
risk engine re-checks the gate on every single trade intent, so no code
path reaches execution without passing it.

Unlocking requires all of the following in `ops/live-gate.json` (see
`ops/live-gate.example.json`):

- At least **30 days** of paper trading against real market conditions.
- **Positive net expectancy** after fees and slippage — not gross P&L.
- Observed max drawdown **within a threshold that was set before the run
  started.** A threshold recorded after the fact fails the check, by design.
- An explicit human sign-off (`approved_by`, `approved_at`).

The gate **fails closed**: a missing file, malformed JSON, or any missing
field leaves live mode locked.

## Architecture

```
src/
  core/       config, domain types, structured logging, the live gate
  risk/       position sizing, slippage cap, stops, daily circuit breaker
  strategy/   strategy modules (empty until Stage 3)
  execution/  the only place that talks to the network or the key (Stage 2+)
  tests/      unit tests — no network access required
```

Two rules shape the layout:

- **Risk has veto power.** `execution/` must call `RiskEngine.approve()`
  before acting on any intent, in *every* mode. The same checks run in
  backtest and paper as in live — otherwise the validation run would be
  evidence about a more permissive system than the one that goes live.
- **Risk is strategy-agnostic.** It consumes a `TradeIntent` and knows
  nothing about how the signal was produced, so v0.2 copy-trading plugs in
  without touching `risk/` or `execution/`.

### Money is `Decimal`, never `float`

Binary floating point cannot represent decimal fractions exactly.
Accumulating that error into P&L means the circuit breaker eventually
compares against a number that is quietly wrong, so every monetary value
is `Decimal` and YAML values are parsed via `str` to avoid inheriting
float error at the boundary.

## Safety behaviours worth knowing

- **The circuit breaker latches.** Once the daily loss limit is hit,
  trading halts for that UTC day and stays halted even if later trades
  would recover the loss. Only a new trading day clears it.
- **It survives a restart.** State persists to disk, so killing the
  process is not a way to clear a halt.
- **Config fails loud.** Unknown keys are rejected (a typo'd risk limit
  must not be silently ignored), and a stop-loss larger than the daily
  loss limit is refused because the breaker could never fire in time.
- **Position size above $10 needs an explicit acknowledgement** in config.
  Typing a bigger number is not enough — that friction is intentional.
- **Logs redact secrets.** Sensitive field names and registered secret
  values are scrubbed from messages, extras, and tracebacks alike.

## Observability

Structured logs are the audit trail. The same redacted payloads are
mirrored to PostHog so behaviour is queryable without a custom dashboard.

Telemetry is **off unless `POSTHOG_API_KEY` is set** — an unconfigured bot
logs exactly as before and sends nothing. A PostHog outage can never
interrupt trading: sink failures are caught and logged, never raised.

Redaction happens once, in `core.logging.redact()`, and the identical dict
goes to both the log and PostHog. There is deliberately no code path that
builds a separate payload for telemetry.

Events currently wired: `risk.blocked` (one per rejection reason),
`risk.daily_halt_triggered`, `gate.live_mode_refused`. The rest of the
schema is marked pending until its call site exists — see
`.claude/skills/posthog-observability/references/event-schema.md`.

**The wallet address is never sent to PostHog.** It is public on-chain
data, but shipping it to a third party links this bot's whole trading
history to one identity in someone else's system. `distinct_id` is the
constant `tradecc-bot`; `tx_signature` is the correlation key when an
event needs to point at a specific transaction; the address itself stays
in local logs. Enforced by `core.telemetry.for_telemetry()`.

## CI

Two workflows, deliberately separated:

| Workflow | Trigger | Gates a PR? |
|---|---|---|
| `test.yml` | Every PR into `main`, push to `main` | **Yes** |
| `contract-tests.yml` | Daily 06:15 UTC + manual dispatch | **No** |

`test.yml` runs the suite on Python 3.11 and 3.12 and enforces a **93%
coverage floor** (current: 94%). The floor moves up, never quietly down.
A PR-only regex scan for secret-shaped strings runs as a second net
beyond the app's own redaction.

`contract-tests.yml` runs the `@pytest.mark.network` tests against real
provider APIs. It is a **drift detector, not a merge gate** — a third
party's outage says nothing about whether your diff is correct, and a CI
gate that fails for reasons the author cannot fix teaches people to
ignore CI. Network tests are excluded from the default `pytest` run, so
the unit suite always passes offline.

## The strategy

`strategy_momentum.py` — EMA crossover with an RSI filter:

- **BUY** when the fast EMA crosses above the slow EMA and RSI is not
  already overbought.
- **SELL** on a downward crossover, or when RSI is overbought.
- **HOLD** otherwise.

Four properties are enforced by tests rather than left to convention:

- **A strategy is a pure function of closed candles.** No I/O, no clock,
  no randomness — a signal's timestamp is the candle's, never `now()`. A
  strategy that consulted the wall clock could not be replayed, and the
  validation gate would be measuring something other than what runs live.
- **No look-ahead.** A test asserts the signal at bar N is identical
  whether or not later bars exist. Indicators return lists aligned to
  their input, with `None` during warmup, because a shorter list silently
  misaligns against candles — the classic way look-ahead creeps in.
- **Crossovers are events, not states.** "Fast is above slow" stays true
  for a whole trend; acting on it every bar would re-enter continuously
  and pay the full cost stack each time. A test walks past a cross and
  asserts the following bars stay HOLD.
- **Nothing signals on thin history.** Below `minimum_candles` the answer
  is always HOLD — a signal from a half-warmed indicator is a signal from
  noise.

Indicators are hand-rolled in `Decimal` rather than taken from pandas.
pandas computes in float64, and a signal that depends on float rounding
can differ between a backtest and the live run meant to reproduce it.
They are tested against independently derived reference values, not
against their own output. pandas is still a fine choice for Stage 4
*analysis*; it is the signal path specifically that stays exact.

Adding a strategy means one module and one line in `strategy/registry.py`
— nothing in `execution/` or `risk/` changes. An unknown strategy name is
a hard error, never a silent fallback to a default.

## Backtesting

`backtest/runner.py` walks candles bar by bar: strategy → risk → simulated
fill. Three properties make the output worth trusting:

- **The same risk engine runs.** Position sizing, slippage cap, stops and
  the daily circuit breaker all apply exactly as they would live. A
  backtest that skipped them would measure a more permissive system than
  the one that trades.
- **No look-ahead.** The strategy sees `candles[:i+1]`, never `i+1`. Fills
  happen on the same bar that produced the signal, adjusted *adversely*
  for slippage — buys fill higher, sells lower.
- **Isolated state.** Risk state is in-memory per run, so a circuit-breaker
  halt in one backtest cannot leak into the next and make results depend
  on the order they were run in.

Candles are cached to disk, so a backtest is reproducible and runnable
offline — re-running against silently different data is a good way to
"discover" an improvement that is really just a different sample.

**Slippage in backtests is assumed, not measured.** Historical candles
carry no quotes. `BacktestConfig.assumed_slippage_pct` keeps the
assumption explicit and configurable rather than buried where a
favourable number could quietly flatter every result. Every report
repeats this caveat.

### First real result (2026-09-09)

SOL/USDC, 1h candles, ~6 weeks, default parameters, $10 positions:

| | |
|---|---|
| Gross P&L | **+$0.32** |
| Fees & costs | **−$0.44** |
| **Net P&L** | **−$0.12** |
| Trades | 15 |
| Win rate (net) | 40% |
| Max drawdown | 1.24% |

The strategy is *gross* profitable and *net* unprofitable: costs are
1.4× the gross edge. That is the entire thesis of this project in one
line, and it does not clear the validation gate. Parameters and interval
have not been tuned — that is Stage 5+ work, and must not be tuned on
this same data.

## Provider rate limits

Every provider is on a free tier, and every one is rate-limited on our
side before the request goes out — free tiers return 429s rather than
failing politely, and discovering a limit mid-position is the worst time
to find it. `core/rate_limit.py` is a sliding-window limiter (fixed
windows permit a double-rate burst across the boundary) shared by all
provider clients.

Jupiter targets the free public host `lite-api.jup.ag`. Moving to the
keyed `api.jup.ag` is a deliberate config change, never a silent fallback
when the free tier throttles.

## Still open before the paper run

- Exact TA parameters and the token watchlist (settled by backtest).
- **The max-drawdown threshold for the validation gate**, which must be
  written to a decision record *before* the 30-day clock starts.
