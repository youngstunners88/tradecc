# TradeCC PostHog Event Schema

Keep this file as the single source of truth for event names and
properties. Update it in the same PR that adds or changes an event —
don't let the code and this file drift apart.

| Event | Fired from | Properties | Status |
|---|---|---|---|
| `mode.changed` | mode transition logic | `from_mode`, `to_mode`, `gate_passed` | **Implemented** — `cli.py` |
| `signal.generated` | strategy module | `strategy`, `signal`, `token`, `params_hash` | Pending — Stage 3 |
| `trade.simulated` | paper-mode execution | `token`, `size_usd`, `modeled_fee_usd`, `modeled_slippage_pct`, `strategy` | **Implemented** — `paper/trader.py` |
| `trade.executed` | live-mode execution | `token`, `size_usd`, `fee_usd`, `slippage_pct`, `tx_signature`, `strategy` | Pending — Stage 6 |
| `risk.blocked` | risk engine | `reason`, `token`, `attempted_size_usd` | **Implemented** — `risk/engine.py` |
| `risk.daily_halt_triggered` | risk engine | `realized_loss_usd`, `threshold_usd` | **Implemented** — `risk/engine.py` |
| `gate.live_mode_refused` | live-trading gate | `reason` | **Implemented** — `risk/engine.py` |
| `rpc.failure` | execution layer | `provider`, `retry_count`, `resolved` (bool) | **Implemented** — `paper/trader.py` |

Events are marked Pending until their call site exists. Wiring an event
before the code that fires it produces a dashboard that looks healthy
because nothing is reporting, which is worse than no dashboard.

`risk.blocked` fires once **per rejection reason**, not once per rejected
trade — a trade blocked by three controls emits three events, so a query
for "how often did the slippage cap bite" stays accurate.

## The wallet address is never sent (decided 2026-09-09)

Settled in `planning/decisions/2026-09-09-stage2-provider-tiers.md`: the
wallet address is sensitive for this project and must not appear in any
PostHog event property.

- `distinct_id` is the constant `"tradecc-bot"` — never a wallet address.
- Use `tx_signature` when an event needs to correlate to a specific
  transaction. It is equally public but identifies one transaction rather
  than the account behind all of them.
- The address stays in local structured logs only.

This is enforced in code by `core.telemetry.for_telemetry()`, which drops
wallet-identifying fields from the telemetry copy of a payload after
redaction. Adding a property named `wallet_address`, `pubkey`,
`public_key`, `owner_address`, or similar will therefore be dropped
silently before send — do not work around it, and do not rename a field
to smuggle the value past the filter.

## Adding a new event
1. Add the row here first.
2. Confirm every property is either non-sensitive (token symbol, dollar
   amounts, public tx signatures) or has been redaction-checked.
3. Confirm it carries no wallet address under any name — see above.
4. Implement using the `log_and_track` wrapper — never call
   `posthog.capture` directly from a new call site.
