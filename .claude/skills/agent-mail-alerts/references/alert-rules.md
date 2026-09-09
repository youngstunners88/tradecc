# TradeCC Alert Rules (draft — confirm thresholds with the user)

| Trigger | Threshold | Batching |
|---|---|---|
| Daily circuit breaker trips | Every time | Immediate, never batched |
| Slippage-cap rejections | 3+ in 60 min | One batched email per window |
| Live-mode gate refusal on user-initiated attempt | Every time | Immediate |
| Unhandled exception in execution/risk path | Every time | Immediate |
| Consecutive RPC failures | 3+ in a row | Immediate, then silence same-cause alerts for 30 min |
| Daily heartbeat | Once per day, fixed time | N/A |

These are starting defaults, not settled values — the batching windows
and failure counts double as risk-tuning knobs, so confirm them with the
user (likely alongside the max-drawdown threshold already flagged as an
open question in `planning/specs/mvp_spec.md`) rather than treating this
table as final.
