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
| 2 | Mocked execution layer + fill simulator | ⬜ Next |
| 3 | Momentum strategy module | ⬜ |
| 4 | Backtest mode (GeckoTerminal data, net-of-fees reporting) | ⬜ |
| 5 | Helius RPC + Jupiter quotes, paper mode | ⬜ |
| 6 | Live execution, gated | ⬜ |
| 7 | Ops, monitoring, deploy | ⬜ |

There is currently **no CLI entrypoint, no network code, and no wallet
handling.** Nothing in this repo can send a transaction.

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
