---
name: copy-trading
description: v0.2 wallet-following — discovering candidate wallets, vetting them for skill rather than luck, and mirroring with a full risk overlay. Use when building wallet discovery, scoring candidates, designing the mirror path, or writing up a candidate in research/wallet-tracking/. Carries the selection-bias protocol, which is the same trap that invalidated the parameter sweep, at far larger N.
---

# Copy-trading (v0.2)

Copy-trading is worth investigating because it is a **genuinely different
alpha source**, not a variant of the momentum strategy that already
failed held-out validation. Its edge, if it exists, comes from someone
else's information rather than from a pattern in the price series.

**Start from the base rate, which is poor.** A 90-day, multi-exchange
study of over 100,000 outcomes found only **~48% of copiers were
profitable**, and — the number that matters most here — while **97% of
leaders were personally profitable, only ~44% produced positive follower
P&L**. Leader profitability is therefore close to uninformative about
follower profitability. That gap is not mysterious: it is the copy lag
and adverse selection described below, measured at scale.

Read that as the null hypothesis this skill has to beat, not as a reason
to skip the work. It means the burden is on a candidate wallet to show
it clears the follower bar, and that "this wallet is up a lot" is the
beginning of the analysis rather than the end of it.

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
- **P&L concentration.** If one trade or one stretch produced most of the
  profit, this is a lottery ticket, not a process. The standing example is
  momentum on 1h: **+$0.58 overall, but the first third of the window
  *lost* money and either remaining third alone exceeded the entire
  pooled result.** (An earlier version cited "+$0.47 on 3 trades" from
  the 2026-09-09 sweep; that figure predates the cost-model correction
  and is superseded.)
- **Consistency across time.** Profitable in most months beats one
  enormous month. A single regime can flatter a wallet exactly as it
  flatters a strategy.
- **Post-cutoff performance, measured against buy-and-hold.** The only
  number that is actually evidence — and "positive" is the wrong bar.
  Momentum cleared positive on 1h (+$0.58) and still lost to simply
  holding SOL over the same window (+$3.93). A wallet that makes money
  more slowly than holding is a worse version of doing nothing. Report
  buy-and-hold over the wallet's own post-T window beside its net, every
  time. See
  `research/backtests/2026-09-11_momentum_lookahead-audit-and-buy-hold-baseline.md`.

### Survivorship bias in the discovery step

Leaderboards and "top trader" endpoints list wallets that *are currently
winning*. Wallets that blew up have left the list. Any population sourced
this way is pre-filtered for luck, which inflates every statistic
computed from it. Note the sourcing method in the write-up, because it
determines how much the numbers can be trusted.

### Point-in-time discipline when replaying a wallet

Cutoff T governs *selection*. It does not, on its own, make the replay
honest. Scoring a wallet's past trades means reconstructing what was
knowable **at each trade's timestamp**, not what is knowable now:

- **Liquidity, holder count and token age must be as-of the trade**, not
  as-of today. A token that is deep and established now may have been a
  thin new pool when the wallet bought it — judging that entry against
  today's depth credits the wallet with a safety it never had.
- **Token survival is knowledge from the future.** Which of its tokens
  later went to zero is precisely what the wallet did not know. Use it to
  compute the rug ratio (a property of the wallet's *record*), never to
  excuse or re-weight an individual entry.
- **Our own copy decision must be reconstructable from data available at
  that timestamp.** If the liquidity gate would have refused the trade
  then, it does not count toward the wallet's copyable record, however it
  turned out.

This is the bug class the 2026-09-11 audit checked the backtest harness
for, and the TradingAgents notes flag it explicitly for wallet history.
The audit found the harness clean; this section exists so copy-trading
does not reintroduce it through a different door.

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

**Decided (2026-09-12): measure copy lag at ≥1m granularity.** The check
wants prices at realistic detection-to-fill latency, which is *seconds*,
but the finest interval the data layer exposes is **1m**
(GeckoTerminal). Rather than quote a sub-minute figure the data cannot
support, the assumption is raised to match the data: **N = 1 minute**.

Be clear about what that costs. A 1m assumption models a **slower
follower than we would actually be**, so it *overstates* copy lag and
will reject some wallets that a faster follower could copy profitably.
That bias is deliberate and it runs the safe way — this skill would
rather discard a viable candidate than admit one whose edge is an
artefact of an optimistic latency guess.

Finer-grained sources exist (trade-level data via Helius parsed
transactions, or Birdeye). **They are deliberately not being evaluated
now.** That work is only worth doing if copy-trading otherwise clears
review *and* the 1m assumption is specifically what blocks a candidate
from passing — i.e. a wallet that fails only on copy lag and would pass
at realistic latency. Anything short of that, and a keyed dependency
buys precision nobody is waiting on.

A wallet whose edge does not survive its own copy lag is not a
candidate, however good its record looks. Always state the granularity
the figure was measured at — which, until the above changes, is 1m.

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
- Trade count, P&L concentration, and measured copy-lag cost at **1m
  granularity** (state it explicitly — the figure is conservative by
  construction, see above).
- **Buy-and-hold over the same post-T window**, beside the wallet's net.
- Red-flag checks, each explicitly checked rather than assumed.
- A verdict, including the case against.

A candidate whose write-up cannot state T and a post-T record is not a
candidate yet. That is the whole discipline in one sentence.
