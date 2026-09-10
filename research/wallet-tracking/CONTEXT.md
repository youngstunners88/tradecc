# Wallet Tracking — CONTEXT.md

## What happens here

Copy-trading candidate research for v0.2, greenlit in
`planning/decisions/2026-09-10-v02-intelligence-architecture.md`.

**No copy-trading execution is built against a wallet that does not have
a completed write-up in this directory.** That rule predates the greenlight
(`research/CONTEXT.md`) and survives it.

## The one rule that matters

Ranking wallets by past P&L and taking the top one finds **the luckiest
wallet, not the best one**. Across a large scan, spectacular records
occur by chance — that is arithmetic. This is the same error that
invalidated the parameter sweep, at much larger N.

So, exactly as with parameters:

> **Pick on history up to a cutoff date T fixed in advance. Evaluate on
> what happened after T. One shot, no re-picking.**

A wallet selected on its full history has no out-of-sample record left
and cannot be validated. Fix T before looking.

## Required fields in a write-up

File as `YYYY-MM-DD_<address-prefix>.md`. Minimum contents:

**Discovery**
- Address.
- How it was found, and **how many wallets were scanned** to surface it.
- Whether the source was a leaderboard — if so, note that the population
  is pre-filtered for survivors and every statistic below is inflated.

**Protocol**
- Cutoff date **T**, and confirmation it was fixed before evaluation.

**Pre-T statistics** (selection basis)
- Trade count — **always beside win rate**; 70% over 20 trades is
  consistent with a coin flip.
- Win rate, max drawdown, median hold time.
- P&L concentration: did one trade produce most of the profit?
- Consistency: profitable across most months, or one enormous month?

**Post-T statistics** (the only actual evidence)
- Same fields, computed on data not used for selection.

**Measured copy-lag cost**
- The wallet's entry price versus the price available N seconds later, at
  realistic detection-to-fill latency. Subtract before scoring.
- A wallet whose edge does not survive its own copy lag is not a
  candidate, however good the raw record looks.

**Red-flag checks** — each explicitly checked, never assumed
- Wash trading / self-directed volume.
- Rug-token ratio.
- Illiquid-token concentration (see below).
- Unreproducible entries — same-block-as-creation entries mean access you
  do not have, so you arrive late every time.

**Verdict** — including the case against.

## Adversarial risk

A wallet with known followers can buy an illiquid token, let copiers push
it up, and sell into them. On-chain this is indistinguishable from a
winning trade until you are the exit liquidity. `2026-09-09-strategy-and-
stack.md` flagged copy-trading counterparty risk; this is its on-chain form.

Mitigations are all refusals: a hard liquidity floor, position capped as
a fraction of pool depth rather than only in dollars, minimum token age
and holder count, and never copying into a token the wallet created.

## Data sources

On-chain history — win rate, drawdown, hold time — comes from **Helius or
Birdeye**, never from scraping. Per `web-research-vetting`, scraped
sources are qualitative supplement only: does the wallet's public
presence match its on-chain behaviour.

Neither `HELIUS_API_KEY` nor `BIRDEYE_API_KEY` is set in the current
environment; `FIRECRAWL_API_KEY` is.

## What a completed write-up does not authorise

A candidate verdict makes a wallet eligible for **paper trading**, not
live. Copy-trading does not inherit momentum's validation: it runs the
full 30-day gate in `core/gate.py` like anything else, and its trades go
through `RiskEngine.approve()` unchanged.
