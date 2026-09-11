---
name: market-intelligence
description: TradeCC's market data layer — the bot's eyes and ears. Use whenever adding a data source, deciding what a signal may condition on, replacing an assumed constant with a live measurement, or gating a trade on liquidity and price impact. Covers the verified free/keyed source table, multi-source corroboration, and the rule that data informs a deterministic strategy but never bypasses the risk engine.
---

# Market Intelligence — the data layer

The bot's job is not to predict price. It is to **decline the trades it
should not take** and to size the rest against measured, not assumed,
conditions. Almost all of the value in this layer comes from the first
half of that sentence.

## Start here: what measurement did to this layer's own assumptions

This section used to open by asserting that **slippage runs ~0.6% per
round trip, roughly 30× the recurring fees**, citing the 2026-09-09
sweep. That claim was wrong by about two orders of magnitude, and the
thing that proved it wrong was this layer doing its job.

Measured against Jupiter on SOL/USDC:

| Size | Measured `priceImpactPct` |
|---|---|
| $5 | 0.0000% |
| $10 | 0.0044% |
| $50 | 0.0012% |
| $200 | 0.0000% |

The pool holds ~$834M. A $10 trade does not move it. The 0.5% figure the
old number was read from is the slippage **tolerance requested** — the
worst case the route protects against — not a cost incurred. Conflating
a tolerance with a cost is the specific error this layer exists to
prevent.

Three sibling constants were wrong the same way and are now fixed: SOL
price was hardcoded at `200` while trading near `$102` (now taken
per-bar from the data), priority fees were modelled as a flat total
rather than **per compute unit** (understating them ~200,000×), and Jito
tips were counted as zero. `BacktestConfig.assumed_slippage_pct` no
longer exists; it is split into `price_impact_pct` (calibrated from
measurement) and `execution_slippage_pct` (still assumed), so "how much
of this is measured?" has an answer at a glance. Refresh the measured
half with `research/calibrate_costs.py`.

**The thesis survived; only its numbers died.** "Replace a global
assumption with a per-trade measurement, then refuse trades whose
measured cost exceeds their expected edge" was the right instruction —
following it is what exposed four bad inputs at once. A hardcoded market
constant is wrong the day after you write it. Constants that describe
the market belong in the data layer, not in config defaults.

### The strongest argument for declining trades

This layer's first claim is that most of its value is in *not trading*.
The buy-and-hold baseline — required by `backtest.md` from the start,
never actually computed until 2026-09-11 — is the evidence:

| Window | Strategy net | **Buy-and-hold net** |
|---|---|---|
| 1h · Jul 29 → Sep 9 | +$0.58 | **+$3.93** |
| 4h · Mar 27 → Sep 9 | −$0.55 | **+$1.70** |
| 15m · Aug 30 → Sep 9 | −$1.78 | **−$0.28** |

Same costs, same $10 size. **Holding beat trading on every interval**,
and on 15m the strategy lost 6× more than doing nothing. The best
available decision on this data was to decline every trade — which is
precisely the action this layer is built to take. Measure first, and the
refusal often *is* the alpha. See
`research/backtests/2026-09-11_momentum_lookahead-audit-and-buy-hold-baseline.md`.

## Verified sources

Probed 2026-09-10. Re-probe before relying on any row — treat this table
the way `openrouter` treats model IDs, as a snapshot rather than truth.

| Source | Key? | Authoritative for | Status |
|---|---|---|---|
| Jupiter `/swap/v1/quote` | No | **Executable price, `priceImpactPct`, route** | In use |
| Jupiter `/price/v3` (`lite-api.jup.ag`) | No | Spot price, 24h change, pool liquidity | 200 ✅ |
| GeckoTerminal | No | OHLCV history, pool metadata | In use |
| DefiLlama (`api.llama.fi`, `yields.llama.fi`) | No | Protocol TVL, chain flows, pool yields | 200 ✅ |
| Helius | Yes | On-chain truth: balances, parsed tx history, webhooks | Key not set in this env |
| Birdeye | Yes | Token analytics, holder distribution, trader leaderboards | 401 without key |

Note the split. **Everything needed to stop taking bad trades is free
and keyless.** Birdeye and Helius keys buy reach into wallet-level and
holder-level data, which is what copy-trading needs — see the
`copy-trading` skill. Do not buy a tier before the free sources are
fully exploited.

### Which source wins a disagreement

They will disagree — different pools, different staleness, different
definitions of "price."

- **For anything that decides a trade: Jupiter's quote wins.** It is the
  only source quoting a price you can actually execute at, for your
  size. A price you cannot trade on is trivia.
- **For history and indicators: GeckoTerminal.** One source, cached to
  disk, so backtests stay reproducible.
- **For "is this token real": Helius/Birdeye holder and liquidity data.**

Never average two price sources into a third number that is not
executable anywhere. Pick the authoritative one per purpose.

## Corroboration as a safety check, not a signal

A single source that is wrong or stale can move real money. Corroborate
in the **safety** direction only:

- If GeckoTerminal's last close and Jupiter's live price diverge beyond
  a configured threshold, that is a **data-quality halt**, not a trading
  opportunity. Stale or broken data is the most common way a bot trades
  on fiction.
- If a pool's liquidity drops sharply between the signal and the quote,
  **skip the trade.** Do not re-quote in a loop chasing a fill.

Both of these produce a *refusal*. Neither produces a buy. That
asymmetry is deliberate and it runs through this whole layer — see the
`astra-analyst` skill for the same principle applied to model output.

## Liquidity gating

Before any intent reaches the risk engine, the data layer should be able
to answer three questions with live numbers:

1. **What is the real price impact at this size?** From the quote, not a
   constant.
2. **How deep is the pool relative to the position?** A $10 trade in a
   pool with $30k of liquidity is a different animal from the same trade
   in SOL/USDC.
3. **Is the route sane?** A quote routed through four hops in illiquid
   pools carries impact at every hop and more failure modes.

A trade that fails any of these is refused *before* risk sees it. The
risk engine remains the single veto point for **risk** decisions
(`RiskEngine.approve()`); this is a **data-validity** gate upstream of
it. Do not merge the two — a rejection here means "we cannot price this
honestly", which is a different fact from "this exceeds a risk limit",
and collapsing them makes both harder to debug.

## Rate limits and caching

Every source above is a free tier, and free tiers answer abuse with 429s
rather than politeness. Reuse `core/rate_limit.py` — the sliding-window
limiter already shared by the provider clients — for every new client.
Do not write a second limiter.

Cache aggressively, and cache with the **staleness that matters for the
decision**:

- OHLCV: cache to disk, effectively permanent for closed candles. Already
  done by `execution/candle_cache.py`.
- Spot price / liquidity: seconds. Cache to avoid hammering, never to
  the point where a trade prices off a stale number.
- TVL / holder data: minutes to hours. It does not move fast enough to
  justify a call per tick.

The 272k-token price cliff in the `openrouter` skill has an analogue
here: the cost of a data layer is dominated by how carelessly it polls.
Poll on candle close, not on a wall clock.

## Hard boundaries

1. **Data conditions a deterministic strategy; it never becomes the
   strategy.** Everything this layer produces is an input to code that
   can be replayed bar-for-bar. If a signal cannot be reproduced from
   cached data, it cannot be backtested, and an unbacktestable signal
   cannot clear the live gate.
2. **Nothing here bypasses `RiskEngine.approve()`.** A data source is
   never a reason to skip a check. New data can only ever *add* a reason
   to decline.
3. **Never source price from scraping.** Per `web-research-vetting`,
   scrapers are for qualitative signal. Price comes from Jupiter,
   GeckoTerminal, or Helius.
4. **Every new field must be available at backtest time**, or the
   backtest silently becomes a different system than the live bot. If a
   source has no history endpoint, you cannot condition trades on it
   until you have recorded your own history forward.
5. **Register every API key** with `core.logging.register_secret()` at
   startup, and build the redacted URL for logging — follow the pattern
   already in `execution/helius.py`.
