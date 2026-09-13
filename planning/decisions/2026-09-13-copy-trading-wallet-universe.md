# Decision: Copy-trading wallet universe — the rule, and why it cannot be satisfied yet

**Date:** 2026-09-13
**Status:** **BLOCKED — infeasible data infrastructure.** Resolved 2026-09-13.
This carries the same standing as momentum's exhausted verdict: it is a
conclusion, not a pause. No wallet was scored, ranked, or named, and none will
be without a new decision record reopening this one on fresh evidence.

## Why this record exists first

Copy-trading is the only path left open by
`planning/decisions/2026-09-12-kill-ema-rsi-momentum.md`. Wallet selection is
the one place bias can now enter, so the universe rule is fixed **before any
wallet is scored** — the same discipline as
`planning/decisions/2026-09-12-cross-sectional-momentum-protocol.md`, whose
universe was resolved by rule rather than chosen.

As there, the only thing inspected beforehand is **what the data can support**.
That inspection is a property of the data source, not of any strategy result.
As there, it turned out to be decisive.

## The rule this record intended to fix

The `copy-trading` skill states the binding constraint: *"Select on history up
to a cutoff date T. Evaluate on what the wallet did after T."* Every practical
shortcut violates it:

- **Published "smart money" lists and leaderboard endpoints are selected on
  realised performance up to today.** Using one is look-ahead bias introduced
  through the universe rather than the indicator — a defect class the
  2026-09-11 audit went looking for in the signal path and would not have
  caught here.
- **Ranking any set of wallets by past P&L finds the luckiest wallet**, which
  has no edge to inherit. That is arithmetic, and it is the same error as the
  parameter sweep at far larger N.

The one construction that is point-in-time clean by design:

> Fix a pool P. Enumerate every transaction touching P over the reachable
> window. Derive each counterparty's in-pool trade sequence from token balance
> deltas. Select on `[A, T)`, evaluate on `[T, B]`.

It references no performance figure to build the candidate set, and a wallet
that blew up and stopped trading is still in it. Every wallet's history falls
out of a single pass over the pool, so no per-wallet fetching is needed.

## What the data actually supports

**It is not enumerable.** Measured 2026-09-13 against the free public RPC
(`api.mainnet-beta.solana.com`), on the five pools of the 2026-09-12
cross-sectional universe. Rate is derived from the time span covered by the
most recent 1000 signatures; the fetch estimate uses the **0.41 tx/s** sustained
throughput measured in `research/copy_trading_feasibility.py`:

| Pool | tx/day | transactions over 353d | hours to fetch bodies |
|---|---|---|---|
| SOL / USDC | 10,800,000 | 3.81 bn | **2,582,927 h** |
| PUMP / USDC | 200,000 | 70.6 m | 47,832 h |
| MET / USDC | 186,207 | 65.7 m | 44,533 h |
| ORE / USDC | 81,741 | 28.9 m | 19,549 h |
| SPYx / USDC | 41,739 | 14.7 m | **9,982 h** |

The **cheapest** pool in the universe needs roughly **fourteen months of
continuous fetching** to traverse one year of its history. SOL/USDC needs about
295 years.

Two follow-on constructions fail for the same reason:

1. **Sampling the pool to discover wallets, then fetching each wallet's own
   history.** A wallet's own signature list is small enough — but discovery has
   to sample the *early* window to stay point-in-time clean, and
   `getSignaturesForAddress` only pages backwards 1000 at a time. Reaching a
   year back on a pool doing 41,739 tx/day means paging through ~14.7m
   signatures first.
2. **Choosing a quieter pool.** Quieter means thinner, and the universe rule
   already requires ≥ $250k reserves for a reason. Even a hypothetical pool at
   200 tx/day is ~70,600 transactions over the window, or ~48 hours of fetching
   — and that is the optimistic end.

## Conclusion

**The unbiased universe rule cannot be satisfied on the current free data
path.** This is not "copy-trading failed"; it is that the honest version of the
test cannot be conducted with what we have, and the dishonest version — rank a
leaderboard, select on realised performance — produces a number that means
nothing.

Note what this does *not* say. The earlier feasibility probe
(`research/backtests/2026-09-12_copy-trading-feasibility-probe.md`) established
that history depth (353 days), transaction bodies, swap-leg reconstruction and
the cost hurdle (0.35% per round trip at $10) are all fine. **Only discovery is
blocked.** Given a candidate set from somewhere trustworthy, everything
downstream works.

## The options, and the ruling

Three were put forward. The ruling, 2026-09-13:

1. **A vendor "top traders" list** (Helius, Birdeye, or any indexed source that
   ranks wallets by realised performance) — **REJECTED.** It reintroduces the
   exact survivorship bias the point-in-time rule exists to prevent, via a
   vendor instead of a public leaderboard. Paying for the biased list does not
   unbias it. This is not a cost question and it is not reopened by a budget.
2. **Accept a biased universe and label the result** — **REJECTED.** A number
   that can only ever read "not refuted on a survivorship-selected sample" is
   not worth the effort to produce and must never justify capital.
3. **Record it as blocked and stop searching for a workaround** — **ADOPTED.**

Note what is *not* ruled out: a wallet-level indexed source used for
**enumeration** rather than ranking — one that answers "which wallets traded
this pool before date T", with no performance ordering — would satisfy the
rule. No such access is available now, and searching for one is explicitly out
of scope until something changes. That distinction is recorded so a future
reader does not mistake this for a blanket ban on indexed data.

## What this record forecloses

- Scoring, ranking, or naming any wallet. **No wallet has been touched.**
- Deriving a candidate set from any list that was itself produced by ranking on
  realised performance, whatever it is called and whoever sells it.
- Further effort searching for a workaround. The question is settled until new
  evidence — not a new idea — reopens it in a fresh record.
- Quietly relaxing the ≥ $250k reserve floor to find an enumerable pool — that
  trades a measurement problem for a liquidity problem and hides it.

## Limitations recorded before any result exists

- **353 days is roughly one regime.** A pass would mean "not refuted on one
  regime", never "confirmed" — the same ceiling as the cross-sectional test.
- **Copy lag is assumed at ≥ 1 minute** (`copy-trading`, `a6acd03`); the data
  layer's finest interval is 1m, so sub-minute copying cannot be evaluated.
- **In-pool trades only.** Even had enumeration worked, it would show a
  wallet's activity in one pool, not its whole portfolio.
- **Buy-and-hold remains the mandatory benchmark.** It beat momentum on every
  interval and nothing entitles copy-trading to a weaker bar.
