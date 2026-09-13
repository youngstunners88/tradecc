# pump.fun graduation-duration hypothesis — feasibility probe

**Date:** 2026-09-13
**Status:** Feasibility findings only. **No strategy code, no authorisation to
build, no data collected.** The hypothesis was pre-registered after this probe,
on the same date, in
`planning/decisions/2026-09-13-pumpfun-graduation-duration.md` — that record
fixes the rules; it does not start collection.

## Scope flag — this reopens a category that was never in scope

`CLAUDE.md:31` places **"sniping new launches"** explicitly out of scope pending
an explicit ask, and the external-tools registry contains **no pump.fun entry at
all** — the category is *unevaluated*, not rejected.

The hypothesis (enter *after* graduation, conditioned on how long the bonding
curve took to fill) is not literally sniping. That distinction is real, and it
is also exactly the kind of technicality that lets a closed category back in
quietly, so it is recorded rather than relied on. The instruction to explore
this is the explicit ask CLAUDE.md requires; it applies **to this hypothesis
only**.

## The hypothesis, stated for the record

> Slower bonding-curve fills indicate organic demand rather than manufactured
> demand, and predict better post-graduation performance.

`fill_duration = graduation_time − token_creation_time`.

## Q1 — Does a Helius webhook avoid the throughput problem?

**Yes, and it is still useless for testing this today.**

Webhooks are **push and forward-only**. That genuinely dissolves the
enumeration bottleneck which blocked wallet-universe work — no traversal, no
0.41 tx/s ceiling — and the data is point-in-time clean *by construction*,
since each event is observed as it occurs.

But a webhook **has no past**. It cannot deliver an event that already
happened, so it cannot backtest anything; it can only start a clock. Two
further blockers: `api.helius.xyz` returns `401 missing api key` (no key in this
environment), and a webhook needs a persistently reachable HTTPS endpoint,
which a session-scoped one is not.

**The useful finding is that Helius is not needed at all.**

## Q2 — Independent verification, not the qlo repo's numbers

Two keyless sources, each supplying a different half, neither being qlo:

| Source | Supplies | Independent of |
|---|---|---|
| pump.fun v3 API (`frontend-api-v3.pump.fun/coins`) | `created_timestamp`, `complete` flag, `pool_address` | qlo |
| GeckoTerminal | `pool_created_at` (graduation time), post-graduation OHLCV | qlo **and** pump.fun |

Verified working on five 2024-era graduations — e.g. KWIF created 2024-01-25,
its AMM pool created 2024-04-03. Fill duration comes from two providers, so
neither provider can define the variable in its own favour. GeckoTerminal is
already in our stack and contract-tested.

**Throughput is a non-issue:** ~2 calls per token, ~67 minutes for 1,000 tokens
at our configured 30/min. Against the **9,982 hours** that blocked wallet
enumeration, this is not the same class of problem.

## The blocker — two measured caps that collide

1. **GeckoTerminal retains ~184 daily bars.** KWIF graduated 2024-04-03; its
   OHLCV begins **2026-03-14**. Post-graduation performance is measurable only
   for tokens graduating inside roughly the last six months.
2. **pump.fun paginates to ~1,000 rows.** `offset=1000` returns rows;
   `offset=1200` returns none. Newest-first, **1,000 rows spans 24.4 hours**.
3. **No date filtering exists.** Ten candidate parameters — `createdBefore`,
   `created_before`, `before`, `maxCreatedTimestamp`, `endTime`, and their
   `After`/`min`/`start` counterparts — are each **silently ignored**, returning
   responses identical to baseline. They are not rejected; they simply do
   nothing, which is worse, because a caller could believe they worked.

So the reachable sample is either **the last ~24 hours** of graduations, or
**the oldest ~1,000 from January 2024** whose post-graduation window expired
long ago. The middle — graduations 30–120 days old, precisely what measuring
forward performance requires — **is unreachable from either end.**

## Verdict

**Data-clean, cheap, and not testable retrospectively.** This is a different
failure from the wallet universe: that one was impossible in principle at any
budget; this one is a pagination limitation with a straightforward workaround
that costs *time* rather than feasibility.

## The workaround, stated but not started

Forward collection, and notably **polling beats the webhook**:

- 1,000 rows covers 24.4 hours, so a **once-or-twice-daily poll** of the
  newest graduated coins captures the full stream without gaps.
- No API key, no public endpoint, no session dependency — none of the webhook's
  three blockers apply.
- Point-in-time clean by construction: each row is recorded at observation
  time, before any post-graduation performance exists to bias selection on.
- A sample becomes testable once the chosen forward horizon has elapsed —
  weeks, not immediately.

**Not started.** It needed a pre-registered decision record first, at the same
bar as every prior test: walk-forward folds, concentration check, benchmark,
`MIN_POOLED_TRADES` floor, and a stopping rule fixed in advance. An interesting
idea does not get a lighter bar — five hypotheses have already failed against
that bar, and the bar is why those failures were trustworthy.

That record is now written
(`planning/decisions/2026-09-13-pumpfun-graduation-duration.md`): horizon,
tertile split, six pass criteria, stopping rule and interpretation rule are all
fixed against a cohort of **zero observations**. Starting the twice-daily poll
remains a separate, explicit call — it commits weeks before any verdict can
exist.

## What is NOT claimed here

- No claim that the hypothesis is true, or that graduation duration predicts
  anything. Nothing has been measured about performance.
- The qlo repo's own numbers were **not** used as a starting assumption and
  were not consulted for this probe.
- No pump.fun token has been scored, ranked, or recommended.
