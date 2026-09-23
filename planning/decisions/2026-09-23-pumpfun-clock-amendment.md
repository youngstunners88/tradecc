# Amendment to the pump.fun graduation-duration pre-registration — before the first row

**Date:** 2026-09-23
**Amends:** `2026-09-13-pumpfun-graduation-duration.md`
**Rows collected at the time of writing:** **zero.** `research/clocks/pumpfun_graduation.jsonl` does not exist yet.
**Authorisation to start collection:** the user, 2026-09-23 ("create the edge"). The original record left that call to the user.

Everything in the 2026-09-13 record stands **except the two collection
parameters below**, which were found unworkable while building the collector.
No hypothesis, horizon, return definition, cost model, test form, pass
criterion, stopping rule or interpretation rule changes.

## Why an amendment, and why it is not a re-cut

The original record forbids changing rules *after seeing data*. None has been
seen. Both changes below close a hole that would have biased the sample
**against the variable under test**, and both were measured before any
observation existed.

## Change 1 — the population is truncated on the predictor, by a fixed rule

**Found:** pump.fun has no graduation-ordered endpoint. `complete=true` sorted
by `created_timestamp` is ordered by **creation**, and its ~1,050-row cap
reaches back only **~23 hours of creation time** (measured 2026-09-23:
offset 1000 → created 22.0–23.3h ago; offset 1200 → no rows; ~45
graduations/hour). GeckoTerminal's `new_pools` mixes every Solana DEX at about
one pool per second, and its pumpswap listing cannot sort by creation time.

**Consequence if unaddressed:** a coin created 30 hours ago that graduates now
is never in the window. The collector would silently drop the **slowest
fills**, which is the tertile the hypothesis is about.

**Rule (locked):** the cohort is **every graduation with
`fill_duration < 20 hours`**. A fixed cutoff on the predictor is a statement of
scope, applied identically to every coin, and it cannot see the outcome. The
hypothesis is tested **within 0–20h fills**. A result may not be generalised
beyond 20h.

The alternative was rejected: a second, last-trade-sorted query would catch
*some* of the >20h tail, depending on how actively each coin trades. That is a
selection on activity, which correlates with the outcome. Clean truncation is
better than partial capture.

## Change 2 — poll every 2 hours, not every 12

With a ~23h creation window and a 20h fill cutoff, a coin that graduates at
fill *f* stays visible for about `23 − f` hours, **at least ~3h**. A 12-hour
poll would miss every graduation with *f* above ~11h, censoring the slow half
of the range. **Poll interval: 2 hours** (at least 1.5× margin at the cutoff).

## Coverage check (locked) — how a hole is detected, not guessed

Each poll records the creation age of the **oldest row returned**. A poll is
**complete** only if

    oldest_created_age_hours >= 20 + hours_since_previous_poll

Otherwise the poll records a **HOLE** for the uncovered interval. Holes are
never back-filled (original rule, unchanged). If graduation volume grows until
the window cannot reach 20h at any cadence, every poll will say so. That is a
finding, not something to work around.

## Nothing else moves

Horizon 30 days. Return close-to-close from the first full bar after
`pool_created_at`, cost-corrected. Dead tokens priced at realised return,
floored at −100%. Slow vs fast tertile, six criteria, equal-weight benchmark.
Stop at 90 days or 200 matured tokens. One analysis, one verdict. Expected
outcome, as stated on 2026-09-13: most likely no relationship.

No Jev. Nothing from any language model enters the predictor, a filter or a
cohort rule. No key, no wallet, no send. This is observation only.
