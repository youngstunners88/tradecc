---
name: posthog-observability
description: Emit TradeCC's trading, risk, and mode-change events to PostHog so the bot's behavior is queryable and dashboardable without building a custom UI. Use this whenever adding or modifying logging, the risk engine, the live-trading gate, mode transitions, or backtest/paper-trade runs — any place structured logs already exist is a place a PostHog event probably belongs too. Do not use this to decide whether to build a dashboard at all — check with the user first if PostHog's built-in dashboards don't cover the need.
---

# PostHog Observability for TradeCC

TradeCC already has structured, redacted logging (Stage 1). This skill
extends the same events to PostHog so they're queryable over time and
can back dashboards/alerts — without building a custom UI, which is out
of scope for v0.1 per the spec.

## Core rule: redaction travels with the event
Every event sent to PostHog must go through the **same redaction path**
already built for the structured logger — never construct a separate,
un-redacted payload for PostHog. If the logger wouldn't print it, PostHog
doesn't get it either. This includes the wallet address in some contexts
— check with the user on whether wallet address itself counts as
sensitive for their threat model before including it in event
properties.

## Event naming convention
Use a consistent `<domain>.<event>` naming scheme so queries stay simple:

- `mode.changed` — properties: `from_mode`, `to_mode`, `gate_passed` (bool)
- `signal.generated` — properties: `strategy`, `signal` (buy/sell/hold), `token`
- `trade.simulated` — paper-mode hypothetical trade — properties: `token`, `size_usd`, `modeled_fee_usd`, `modeled_slippage_pct`
- `trade.executed` — live-mode real trade — properties: same as above, plus `tx_signature` (this is public on-chain data, not a secret — fine to include)
- `risk.blocked` — a risk control refused a trade — properties: `reason` (slippage_cap / position_size / stop_loss / daily_limit), `token`
- `risk.daily_halt_triggered` — the daily circuit breaker fired — properties: `realized_loss_usd`, `threshold_usd`
- `gate.live_mode_refused` — the live-trading gate correctly refused to run — properties: `reason`

See `references/event-schema.md` for the full property list per event
before adding a new event type — keep it consistent rather than
inventing ad hoc property names per call site.

## Implementation pattern
Wrap the existing redacted logger call, don't replace it:

```python
def log_and_track(event: str, **properties):
    redacted = redact(properties)  # reuse the existing redaction function
    logger.info(event, **redacted)
    posthog.capture(distinct_id="tradecc-bot", event=event, properties=redacted)
```

Call this from the same places structured logs already fire — the risk
engine, the gate, the strategy signal generator, execution — rather than
adding a parallel instrumentation pass later.

## What this replaces
This likely removes the need for V0DEV/Netlify dashboard work in v0.1 —
PostHog's built-in trend/funnel views can show P&L over time, circuit-
breaker frequency, and mode distribution directly. Don't build a custom
dashboard unless the user confirms PostHog's views genuinely don't cover
what they need.
