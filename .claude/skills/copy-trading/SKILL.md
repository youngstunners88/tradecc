---
name: copy-trading
description: v0.2 wallet-following — discovering candidate wallets, vetting them for skill rather than luck, and mirroring with a full risk overlay. Use when building wallet discovery, scoring candidates, designing the mirror path, or writing up a candidate in research/wallet-tracking/. Carries the selection-bias protocol, which is the same trap that invalidated the parameter sweep, at far larger N.
---

# Copy-trading (v0.2)

Copy-trading is worth building because it is a **genuinely different
alpha source**, not a variant of the momentum strategy that already
failed held-out validation. Its edge, if it exists, comes from someone
else's information rather than from a pattern in the price series.

It also carries failure modes momentum does not have, and most of them
are adversarial rather than statistical.

## The trap, stated first

The parameter sweep failed because it took **the maximum of a mostly
negative distribution** and mistook it for an edge. 78–88% of
combinations lost money on their own tuning range; the best-looking one
collapsed out of sample.

Wallet selection is the identical error at much larger N. Scan 10,000
wallets and some will show spectacular records **through chance alone** —
that is arithmetic, not cynicism. Ranking wallets by past P&L and picking
the top one finds *the luckiest wallet*, and the luckiest wallet has no
reason to keep winning.

The defence is the one this repo already uses:

> **Select on history up to a cutoff date T. Evaluate on what the wallet
> did after T, without re-picking.** One shot per candidate, exactly as
> `2026-09-09-tuning-holdout-split.md` requires for parameters.

A wallet chosen on its full history has no out-of-sample record left, and
cannot be validated. Fix T before you look.

## Vetting: skill versus luck

`research/CONTEXT.md` already requires win rate, max drawdown, median
hold time, and red flags logged before a wallet is eligible. Those are
necessary. They are not sufficient, because none of them account for
sample size or for the population the wallet was drawn from.

Add:

- **Trade count, always reported beside win rate.** 70% over 20 trades is
  consistent with a coin flip. Sample size determines whether any of the
  other numbers mean anything, and it is the number most often omitted.
- **Selection-pool size.** "Best of 10,000" and "best of 12" are
  completely different claims about the same win rate. Record how many
  wallets were scanned to surface this one.
- **P&L concentration.** If one trade produced most of the profit, this
  is a lottery ticket, not a process. The sweep's "+$0.47 on 3 trades at
  a 33% win rate" is the cautionary example — one trade carried it.
- **Consistency across time.** Profitable in most months beats one
  enormous month. A single regime can flatter a wallet exactly as it
  flatters a strategy.
- **Post-cutoff performance.** The only number that is actually evidence.

### Survivorship bias in the discovery step

Leaderboards and "top trader" endpoints list wallets that *are currently
winning*. Wallets that blew up have left the list. Any population sourced
this way is pre-filtered for luck, which inflates every statistic
computed from it. Note the sourcing method in the write-up, because it
determines how much the numbers can be trusted.

## Red flags that disqualify outright

- **Wash trading** — self-directed volume manufacturing a track record.
- **High rug-token ratio** — early entries into tokens that later go to
  zero suggests insider flow, not skill, and is not repeatable by a
  follower.
- **Illiquid-token concentration** — see the adversarial section below.
- **Unreproducible entries** — if entries consistently land in the same
  block as token creation, the wallet has access you do not. Copying it
  means arriving late every time.

## Two costs momentum does not have

### 1. Copy lag is a real, measurable cost

You observe a trade after it confirms on chain, then send your own. You
buy **after** they did, into whatever move their trade and every other
copier's trade caused. On a momentum-driven fill, that is adverse by
construction.

Do not estimate this — **measure it**, the same way `market-intelligence`
insists on measured price impact over assumed slippage. For each
candidate, compare the wallet's entry price against the price actually
available N seconds later, where N is your realistic detection-to-fill
latency. Subtract the result from the wallet's reported returns before
scoring it.

A wallet whose edge does not survive its own copy lag is not a candidate,
however good its record looks. This check is cheap and it eliminates most
candidates.

### 2. Being copied is exploitable

A wallet that knows it has followers can buy an illiquid token, wait for
copiers to push the price up, and sell into them. From on-chain data this
is indistinguishable from a winning trade — right up until you are the
exit liquidity.

Mitigations, all of which are refusals:

- **Hard liquidity floor**, from the `market-intelligence` gate. Depth is
  what makes this attack possible; a deep pool cannot be moved by your
  $10 or by the copier pool.
- **Cap position as a fraction of pool liquidity**, not just in dollars.
- **Refuse tokens below a minimum age and holder count.**
- **Never copy into a token the wallet itself created.**

`2026-09-09-strategy-and-stack.md` already flagged counterparty risk as
the reason to self-host wallet-following rather than integrate a hosted
platform. This is the on-chain version of the same risk: the wallet you
follow is a counterparty whose interests may be opposed to yours.

## The mirror path

Copy-trading produces a `TradeIntent` and **nothing else changes**. The
architecture was built for this — `risk/` is strategy-agnostic by design,
per the README and the stack decision record.

Concretely:

- A followed wallet's trade is a **signal**, identical in status to an
  EMA crossover. It is not an instruction.
- Position size is **ours**, from `RiskConfig` — never a proportion of
  theirs. They may be trading a size that makes their strategy work and
  ours impossible.
- `RiskEngine.approve()` runs unchanged: slippage cap, stop-loss, daily
  circuit breaker. A copied trade that breaches a limit is refused. There
  is no "but the wallet is good" override, in the same spirit as the
  `openrouter` skill's "no 'the model was confident' override."
- **Our exits are ours.** Stop-loss and take-profit fire on our rules. Do
  not wait for the followed wallet to exit — they may hold through a
  drawdown we cannot afford, or exit into liquidity we do not have.
- Everything runs in **paper mode first**, through the same 30-day gate.
  Copy-trading does not inherit momentum's validation, and it does not
  get its own shortcut.

## Data requirements

Wallet-level history needs a key: **Helius** (parsed transaction history,
plus webhooks for live following) or **Birdeye** (trader leaderboards,
holder data). Neither key is set in the current environment.

Per `web-research-vetting`, scraped sources are **qualitative supplement
only** — win rate, drawdown, and hold time come from on-chain history via
a proper API, never from a leaderboard page. Now that v0.2 is greenlit,
Firecrawl is available for the qualitative half (does a wallet's public
presence match its on-chain behaviour), and a `FIRECRAWL_API_KEY` is
present in this environment.

## Logging requirement

Per `research/CONTEXT.md`, no execution is built against a wallet that
has not been written up in `research/wallet-tracking/` first. A write-up
must carry, at minimum:

- Address, and **how it was discovered** (including pool size scanned).
- **Cutoff date T**, fixed before evaluation.
- Pre-T stats and post-T stats, reported separately.
- Trade count, P&L concentration, and measured copy-lag cost.
- Red-flag checks, each explicitly checked rather than assumed.
- A verdict, including the case against.

A candidate whose write-up cannot state T and a post-T record is not a
candidate yet. That is the whole discipline in one sentence.
