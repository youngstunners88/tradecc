# Copy-trading feasibility probe — is the hypothesis testable at all?

**Date:** 2026-09-12
**Harness:** `research/copy_trading_feasibility.py`
**Run before:** any copy-trading decision record exists. That is the point.

Copy-trading is the only named, untested signal source left after
`planning/decisions/2026-09-12-kill-ema-rsi-momentum.md`. Twice this session,
measuring *whether a hypothesis is testable* before writing its protocol has
saved the protocol entirely — regime-detection died on an empty trend arm,
cross-sectional momentum was capped at five names by history depth. This probe
applies the same discipline to the last remaining path.

It scores no wallets and proposes no universe.

## Verdict

**Copy-trading is not killed by data availability, and it is not killed by
costs.** It is blocked on one thing: **constructing a wallet universe without
survivorship bias.** That is a design problem, not a data problem, and it is
the whole ballgame.

## Q1 — History depth: sufficient

Free public RPC (`api.mainnet-beta.solana.com`), paginating
`getSignaturesForAddress`:

| Page | Signatures | Oldest reached |
|---|---|---|
| 1 | 1000 | 2026-08-01 |
| 2 | 1000 | 2026-06-17 |
| 3 | 1000 | 2026-04-17 |
| 4 | 1000 | 2025-12-21 |
| 5 | 1000 | 2025-10-03 |
| 6 | 1000 | 2025-09-24 |

**6000 signatures reaching 353 days back.** This was the expected killer — most
public RPC nodes prune aggressively — and it is not. A year of history supports
a selection window plus multiple out-of-sample folds.

**No API key was used or needed.** `HELIUS_API_KEY` is not set in this
environment and `mainnet.helius-rpc.com` returns `Unauthorized` without one, so
every number here characterises the *free* path.

## Q2 — Transaction bodies: retrievable, and swaps are derivable

`getTransaction` at depth returns a full body, with 6 pre- and 6
post-token-balance entries. **Swap legs — which mint in, which out, what
amounts — are derivable from token balance deltas**, with no paid parsed-
transaction API and no new dependency.

## Q3 — Throughput: slow, and this is the real cost

| Measure | Value |
|---|---|
| Sustained rate | **0.41 tx/s** |
| Rate-limit retries | 8 per 12 calls |
| One wallet-year (~6000 tx) | **≈ 4.1 hours** |
| Ten wallets | **≈ 41 hours** |

One `getTransaction` per signature is unavoidable on the free path. This is
tolerable as a one-off cached extraction and intolerable as anything
interactive. It also means **enumerating a broad wallet universe by scanning is
off the table** — which is exactly what makes Q4's selection problem bite.

## Q4 — Cost hurdle: much lower than a first pass suggests

Per round trip, recurring costs only:

| Size | Recurring RT | Fee % | Adverse % | **Hurdle** |
|---|---|---|---|---|
| $5 | $0.0127 | 0.25% | 0.22% | **0.47%** |
| $10 | $0.0127 | 0.13% | 0.22% | **0.35%** |
| $25 | $0.0127 | 0.05% | 0.22% | 0.27% |
| $100 | $0.0127 | 0.01% | 0.22% | 0.23% |

**A correction, recorded because it nearly became a false conclusion.** A first
pass at this table counted ATA rent as a fee and produced a hurdle of **2.42%
at $10 and 4.63% at $5** — high enough to kill copy-trading on economics alone.
That is wrong. ATA rent is a **refundable rent-exempt deposit**, charged once
per mint and recoverable on close; `costs.py` says so explicitly in
`TradeCosts.recurring_usd` and warns against precisely this conflation. The
correct hurdle at $10 is **0.35%**, roughly seven times smaller.

What rent *does* cost is capital lockup: **$0.2076 per distinct mint held, or
2.1% of a $10 account** per concurrent position. Real, bounded, recoverable —
not a fee.

## What actually blocks this

Not data. Not cost. **Wallet selection.**

To test copy-trading honestly you must select wallets by a rule applied at a
point in time, then evaluate forward. Every practical shortcut violates that:

- **Any published "smart money" or leaderboard list is selected on realised
  performance up to today.** Copying it into a backtest is look-ahead bias by
  construction — the same defect class the 2026-09-11 audit went looking for,
  reintroduced through the universe instead of the indicator.
- **Enumerating candidates by scanning is infeasible** at 0.41 tx/s (Q3).
- Which leaves: derive the candidate set from something that does not reference
  performance. The tractable version is a **pool's counterparties during a
  fixed early window** — one address to enumerate, and the traders fall out of
  its transaction history. Rank them on a training window, evaluate forward on
  held-out folds.

That design is point-in-time clean and fits inside 353 days. It is **not**
proposed here. It is the thing a decision record would have to fix, in advance,
along with the fold structure, the trade-count floor, the benchmark, and the
stopping rule.

## Recorded limitations, before any result exists

- **Survivorship is only partly solvable.** Wallets that blew up and stopped
  trading may not appear in a late-window pool scan. A universe drawn from an
  *early* window and followed forward is the honest construction.
- **Copy lag is settled at ≥ 1 minute** (`copy-trading` skill, `a6acd03`). The
  data layer's finest interval is 1m, so sub-minute copying cannot be
  evaluated, only assumed away.
- **353 days is roughly one regime.** The same limitation that capped the
  cross-sectional test applies, and a pass would again mean "not refuted on one
  regime", never "confirmed".
- **Buy-and-hold remains the mandatory benchmark.** It beat momentum on every
  interval and nothing entitles copy-trading to a weaker bar.
