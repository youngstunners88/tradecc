---
name: copy-wallet-bitquery
description: Point-in-time wallet book extraction and copy-signal construction for TradeCC via Bitquery. Use when building or reviewing copy-trading research, universe files, strategy_copy.py, or a DeepSeek work order for any of them. Emits paper TradeIntents only. Never live-sends. Never uses leaderboards as a universe.
---

# Copy-wallet via Bitquery

This skill reopens **one blocked category, for data collection only**.
Copy-trading was blocked because free RPC could not enumerate a
point-in-time-clean universe at 0.41 tx/s — roughly 9,982 hours of crawling.
Bitquery is a data layer that may remove that specific blocker.

Be precise about what that does and does not mean:

- It **does not** reopen directional prediction. That is closed as a *class*
  (`2026-09-14-close-directional-prediction-class.md`) and no data source
  changes the required accuracy.
- It **does not** unlock live mode. `src/core/gate.py` is untouched.
- It **does not** make copy-trading a known edge. The inventory verdict stays
  **Blocked** until Phase A produces numbers. Removing the reason something
  was untestable makes it *testable*, not *true*.

## What "practical" means here

Practical = a frozen universe → a ranked allowlist → a deterministic
`strategy_copy.py` emitting `TradeIntent`s into the **existing paper loop**,
through the same `RiskEngine.approve()` path momentum used, with simulated
fills and the gate untouched.

Not practical = a chat session concluding "this wallet is good, copy it."
Not allowed = any model, DeepSeek or otherwise, sending a swap.

## Hard rules

1. **The selection window closes before ranking begins.** Addresses first
   seen after `selection_end` are dropped. Leaderboards, GMGN/Fomo "top
   traders", and any list ranked on all-time PnL up to today are **forbidden
   as a universe** — they are survivorship bias with a UI. The wallets on
   them are there *because* they won, which is the fact under test.
2. **Bitquery is read-only data.** `BITQUERY_API_KEY` lives in the
   environment, registered before use like every other key in this project.
   Never in git, prompts, logs, or DeepSeek context.
3. **Copy lag ≥ 60s**, applied by timestamp comparison inside the strategy so
   it binds identically in backtest and paper. Sub-minute is out of scope
   until the data resolution supports it — the finest interval available here
   is 1m, and claiming a 10s lag against 1m bars is a fiction.
4. **Net of `src/execution/costs.py`.** The headline number is net expectancy
   after lag and costs. Recurring costs go in the hurdle; ATA rent is a
   refundable lockup and goes in the write-up.
5. **Same replication rule as `.claude/skills/backtesting`.** Expanding
   3-fold walk-forward; a pass needs net > 0 in ≥ 2 of 3 folds, pooled
   net > 0, no single fold contributing > 60% of pooled net, and pooled
   trades ≥ 12.

   ⚠️ **But 12 is not enough here, and the viability gate proved it.**
   `research/copy_wallet/PHASE_A_VIABILITY_DRAFT.md` shows the detection
   floor is 13.88 round trips even for a *perfect, zero-lag* copy, and that
   12 pooled trades would only suffice if the copy retained 107.6% of the
   source move — impossible. With a real 60s lag the requirement runs from
   ~56 round trips (at 50% retention) to ~1,388 (at 10%). Do not treat a
   12-trade pass as a Phase A result.
6. **Buy-and-hold of the same cash is the mandatory benchmark.** Momentum
   died on exactly this comparison. A copy strategy that makes money and
   still loses to holding SOL has not found an edge.
7. **No Stage 6 send from this skill.** `strategy_copy` stops at intent.
8. **DeepSeek drafts; Claude Code and the human verify.** Every numeric claim
   is re-derived by a script before it is believed. Provenance header
   required on every artifact.

## Universe construction

The pool-counterparty method, from
`research/backtests/2026-09-12_copy-trading-feasibility-probe.md`:

1. Pick 1–3 high-volume SOL/USDC (or SOL/USDT) pools.
2. `selection_window` = a **closed early interval** inside available history.
3. Candidates = distinct addresses that swapped against those pools **in that
   window only**.
4. Rank candidates on a **later training window**.
5. Evaluate on held-out folds after training ends.

Bitquery replaces the crawl. **It does not replace the window discipline** —
the discipline is what makes the result mean anything, and it is cheap.

Filtering must be **performance-blind at selection time**. Dropping known
*program* IDs with a static list is fine; dropping addresses because they
lost money is the bias this method exists to avoid.

## Delegating the build

The heavy implementation goes to DeepSeek via
`.claude/skills/openrouter-deepseek`. The work order is
`planning/prompts/DEEPSEEK_COPY_WALLET_BUILD.md`; the supervisor role is
`planning/prompts/CLAUDE_WHILE_DEEPSEEK_BUILDS.md`.

**`src/` is not sendable to DeepSeek**, and that rule does not get an
exception here. `research/copy_wallet/INTERFACE_BRIEF.md` is the hand-written
substitute: it carries the strategy protocol, the types, the registration
pattern and the cost API as text in an allow-listed location. Keep it in step
with `src/` or it goes stale silently.

## The one thing most likely to go wrong

`Strategy.generate()` is **a pure function of closed candles**. Copying needs
source fills, and the obvious implementation fetches them inside `generate()`
— which destroys replayability and makes the backtest measure something other
than what runs. The fill log must be **frozen and injected at construction**,
with eligibility decided by comparing `fill.timestamp + lag` against
`candles[-1].timestamp`.

This is also where look-ahead enters if it enters at all. A lag applied at
fetch time has not been applied.

## Status discipline

Do not move copy-trading to "Open" in `structural-edge-inventory` until
Phase A has numbers. A footnote recording the data-collection reopen is
correct; changing the verdict is not. The ledger's value is that its verdicts
mean something, and a verdict changed on hope is a verdict nobody can trust.
