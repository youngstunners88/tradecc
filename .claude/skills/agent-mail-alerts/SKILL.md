---
name: agent-mail-alerts
description: Send email alerts via AgentMail for TradeCC's safety-critical events — daily circuit breaker trips, repeated stop-loss triggers, RPC/Helius failures, and any live-mode transition. Use this whenever building or modifying the risk engine's failure paths, the live-trading gate, or anything in ops/monitoring — a risk control that fires silently in a log file is much less useful than one that also reaches the user. Also use this to set up a daily heartbeat email so a missing digest itself signals a problem.
---

# AgentMail Alerts for TradeCC

The ops spec calls for alerting when the daily circuit breaker trips.
Structured logs (and PostHog) are for querying after the fact — email is
for "the user should know about this now, even if they're not watching
a dashboard."

## What must trigger an alert
- `risk.daily_halt_triggered` — always. This is the most important
  alert in the system; if this fires and no email goes out, that's a
  bug worth treating with the same seriousness as a failed risk check.
- Repeated `risk.blocked` events for the same reason within a short
  window (e.g., 3+ slippage-cap rejections in an hour) — may indicate
  market conditions the strategy wasn't built for, not just normal
  filtering.
- `gate.live_mode_refused` on an attempt to actually start live mode —
  the user tried to go live and got refused; they should know why
  immediately, not discover it by reading logs later.
- Any unhandled exception in the execution or risk path.
- Sustained RPC failures (e.g., 3+ consecutive Helius failures) —
  distinguish this from a single transient retry, which shouldn't spam
  an email.

## What must NOT go in an alert email
Same redaction rule as logging and PostHog: never include the wallet
private key, seed phrase, or anything key-shaped. Reference the token,
dollar amounts, and a pointer to the log entry / PostHog event — not
raw secrets. Also avoid pasting full transaction payloads; a tx
signature (public data) is fine, the signed transaction blob is not
necessary and adds noise.

## Rate limiting
Don't let a repeated failure spam the inbox. Batch same-type alerts —
e.g., "3 slippage rejections in the last hour" as one email, not three.
See `references/alert-rules.md` for the specific thresholds to implement
before wiring this up; confirm them with the user rather than picking
arbitrary numbers, since they double as risk-tuning parameters.

## Daily heartbeat
Send one summary email per day regardless of whether anything went
wrong — trade count, P&L (paper or live), any risk-control triggers,
current mode. If a day passes with no heartbeat email, that's itself a
signal something's broken (the bot crashed, the scheduler died, etc.) —
this is a cheap and valuable safety net for an unattended bot.
