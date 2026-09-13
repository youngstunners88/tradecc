# Decision: Provider Tiers, Telemetry Scope, and Contract-Test Placement (2026-09-09)

## Context
Three decisions taken ahead of Stage 2 (Helius RPC + Jupiter quotes). All
three were the user's calls; this record captures them and the reasoning
so they are not silently revisited later.

## 1. Jupiter: free public tier, rate-limited like every other provider

**Decision:** target Jupiter's free public host and apply a client-side
rate limit to it, rather than assuming the free tier has headroom.

- Free/public host: `https://lite-api.jup.ag` — verified 2026-09-09 to
  serve `/swap/v1/quote` with no API key.
- Keyed host: `https://api.jup.ag`. Moving to it is a deliberate config
  change (`providers.jupiter_base_url`), never a silent fallback when the
  free tier throttles. A fallback that quietly starts spending money is
  the wrong shape for this project.

**Why limit a tier whose published ceiling we have not confirmed:** free
tiers do not fail politely. They return 429s, and a bot that discovers
its limit by being throttled mid-position finds out at the worst possible
moment. The limit is therefore enforced on our side, before the request
goes out, for GeckoTerminal, Helius, and Jupiter alike.

`providers.jupiter_max_requests_per_minute` defaults to a conservative 60.
**This number is a placeholder, not a verified ceiling** — Jupiter's
published free-tier limit should be confirmed when the quote client is
built, and this record superseded if it differs. Configured and wrong is
recoverable; assumed and unlimited is not.

**Implemented now:** `core/rate_limit.py` — a sliding-window limiter with
injectable clock and sleep. Sliding rather than fixed, because a fixed
window lets a caller fire a full quota at the end of one window and again
at the start of the next: a burst of double the intended rate, which is
precisely what trips a throttle.

## 2. Wallet address is withheld from telemetry

**Decision:** the wallet address is sensitive for this project. It is
never sent to PostHog.

- `distinct_id` stays the constant `"tradecc-bot"` — never a wallet.
- `tx_signature` is the correlation key when an event must point at a
  specific transaction. Equally public, but it identifies one transaction
  rather than the account behind every transaction.
- The address itself stays in local structured logs only.

**Reasoning:** the address is public on-chain data, so this is not
secret-handling in the sense of CLAUDE.md rule 1. The concern is
different: shipping it to a third party links this bot's entire trading
history to a single identity inside someone else's system, permanently
and outside our control. Cheap to withhold, expensive to undo.

**Implemented now:** `core.telemetry.for_telemetry()` drops locals-only
fields from the already-redacted payload. Redaction still happens once, in
`core.logging.redact()`, and both copies derive from it — telemetry can
never carry something the log would have masked. This is a further
narrowing of the telemetry copy, not a second redaction path.

## 3. Network contract tests never gate a PR

**Decision:** tests marked `@pytest.mark.network` run in their own
scheduled workflow (daily at 06:15 UTC, plus manual dispatch), excluded
from the default test run and from PR CI.

**Reasoning:** these tests exist to detect *provider drift* — an API
whose shape changed under us. That is worth knowing within a day. It is
not worth blocking a merge on, because a third party's outage says
nothing about whether our diff is correct, and a CI gate that fails for
reasons the author cannot fix teaches people to ignore CI.

- Default run and PR CI: `-m "not network"`, set in both `pyproject.toml`
  and explicitly in the workflow.
- Contract workflow: no coverage gate — coverage is the unit suite's job.
- Missing provider secrets cause affected tests to **skip**, not fail, so
  the keyless free-tier endpoints still get checked.

## Consequences
- `RunConfig` gains a `providers` section. Provider base URLs are
  validated as HTTPS.
- Stage 2's execution clients take a `RateLimiter` rather than each
  inventing their own throttling.
- `.claude/skills/posthog-observability/references/event-schema.md` records
  the wallet-address rule so a future event cannot reintroduce it.

## Still open
- Jupiter's actual published free-tier rate limit (see above).
- Helius free-tier request ceiling — same treatment, same placeholder
  caveat.
