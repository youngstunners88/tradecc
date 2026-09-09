# TradeCC PostHog Event Schema

Keep this file as the single source of truth for event names and
properties. Update it in the same PR that adds or changes an event —
don't let the code and this file drift apart.

| Event | Fired from | Properties | Status |
|---|---|---|---|
| `mode.changed` | mode transition logic | `from_mode`, `to_mode`, `gate_passed` | Pending — no mode-transition code yet |
| `signal.generated` | strategy module | `strategy`, `signal`, `token`, `params_hash` | Pending — Stage 3 |
| `trade.simulated` | paper-mode execution | `token`, `size_usd`, `modeled_fee_usd`, `modeled_slippage_pct`, `strategy` | Pending — Stage 2 |
| `trade.executed` | live-mode execution | `token`, `size_usd`, `fee_usd`, `slippage_pct`, `tx_signature`, `strategy` | Pending — Stage 6 |
| `risk.blocked` | risk engine | `reason`, `token`, `attempted_size_usd` | **Implemented** — `risk/engine.py` |
| `risk.daily_halt_triggered` | risk engine | `realized_loss_usd`, `threshold_usd` | **Implemented** — `risk/engine.py` |
| `gate.live_mode_refused` | live-trading gate | `reason` | **Implemented** — `risk/engine.py` |
| `rpc.failure` | execution layer | `provider`, `retry_count`, `resolved` (bool) | Pending — Stage 5 |

Events are marked Pending until their call site exists. Wiring an event
before the code that fires it produces a dashboard that looks healthy
because nothing is reporting, which is worse than no dashboard.

`risk.blocked` fires once **per rejection reason**, not once per rejected
trade — a trade blocked by three controls emits three events, so a query
for "how often did the slippage cap bite" stays accurate.

## Adding a new event
1. Add the row here first.
2. Confirm every property is either non-sensitive (token symbol, dollar
   amounts, public tx signatures) or has been redaction-checked.
3. Implement using the `log_and_track` wrapper — never call
   `posthog.capture` directly from a new call site.
