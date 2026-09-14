# TradeCC Alert Rules (draft — confirm thresholds with the user)

| Trigger | Threshold | Batching |
|---|---|---|
| Daily circuit breaker trips | Every time | Immediate, never batched |
| Slippage-cap rejections | 3+ in 60 min | One batched email per window |
| Live-mode gate refusal on user-initiated attempt | Every time | Immediate |
| **Live-gate state change** (unlock, re-lock, fingerprint mismatch, failure set changes) | Every transition | Immediate, never batched |
| Unhandled exception in execution/risk path | Every time | Immediate |
| Consecutive RPC failures | 3+ in a row | Immediate, then silence same-cause alerts for 30 min |
| Daily heartbeat | Once per day, fixed time | N/A |

These are starting defaults, not settled values — the batching windows
and failure counts double as risk-tuning knobs, so confirm them with the
user rather than treating this table as final.

**The live-gate row is the exception: it is implemented and its rule needed
no arbitrary number.** `core.gate_watch` alerts on *transitions*, so a steady
gate is silent and there is no window to tune. That is better than a time-based
throttle, which can suppress a genuine change that happens to land during a
quiet period. See `src/core/gate_watch.py` and
`planning/decisions/2026-09-13-max-drawdown-threshold.md`.
