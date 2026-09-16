> **Provenance:** DeepSeek-assisted (`deepseek/deepseek-v4-pro-0813` via OpenRouter, 2026-09-16).
> Drafted by the model. **Not yet reviewed** — review and independently
> re-derive every numeric claim before adopting this, and replace this
> line with the reviewed form from
> `.claude/skills/openrouter-deepseek/SKILL.md` once you have.
>
> Sources supplied to the model: `planning/prompts/DEEPSEEK_COPY_WALLET_BUILD.md`, `.claude/skills/copy-wallet-bitquery/SKILL.md`.

# Conditional reopen of copy-trading via Bitquery (data collection only)

**Date:** 2026-09-16 — decision-record date only. No backtest, selection-window, training-window, or fold date is set here; all protocol dates are deliberately `TBD`.

**Status:** Conditional reopen of **data collection only**. The structural-edge inventory verdict for copy-trading remains **Blocked** until Phase A produces numbers. This does **not** reopen directional prediction, and it does **not** unlock live mode.

## Decision

Copy-trading research is conditionally reopened solely as a data-collection and paper/backtest exercise using Bitquery to enumerate a point-in-time-clean wallet universe under a frozen, pre-committed protocol; if the frozen Phase A protocol fails replication, the reopen is abandoned rather than tuned.

## Reasoning

Copy-trading was blocked not on an economic verdict, but because free RPC enumeration of a point-in-time-clean wallet universe runs at roughly 0.41 tx/s. *(The draft flagged this as asserted-but-unverified, because the measuring file was not in its context. On review it checks out: `research/backtests/2026-09-12_copy-trading-feasibility-probe.md:56` records a measured sustained rate of 0.41 tx/s, and line 100 draws the same conclusion — enumerating candidates by scanning is infeasible at that rate.)* Bitquery may remove that crawl bottleneck. Removing the reason something was untestable makes it **testable**, not **true**. The inventory verdict must not move to Open until Phase A has replication numbers.

The single most important design choice is to freeze one ranking rule before any result is seen. The ranking metric is:

> training-window realised net PnL ÷ max drawdown.

This metric is **fixed, not searched**.

That matters because a grid over candidate metrics — total PnL, win rate, profit factor, Sharpe, PnL/maxDD, etc. — would manufacture a winner from noise. On the same fixed history, some metric will look good even if none has out-of-sample value. At that point the folds are no longer independent tests; they are being used to select the test. A single metric chosen in advance keeps the experiment a single test. If that metric fails, the correct conclusion is that the method failed, not that a different metric should be tried.

## Frozen protocol

The following are frozen before any Phase A result is seen:

- **Universe method:** Bitquery DEX trades against named pool(s). Candidates are unique trader/account addresses appearing in pool trades **inside the selection window only**. Known program IDs may be dropped via a static allow/deny list. No address may be dropped for being unprofitable. Selection must be performance-blind.
- **Selection window:** `TBD`–`TBD`.
- **Training window:** `TBD`–`TBD`.
- **Fold boundaries:** `TBD`, fixed after extractor output; expanding 3-fold.
- **Ranking metric:** training-window realised net PnL ÷ max drawdown. Fixed, not searched.
- **N wallets:** top 3, cap.
- **Lag:** 60 seconds, applied as `fill.timestamp + 60s` compared against `candles[-1].timestamp`. Sub-minute lag is rejected because the available bar interval is 1m, and claiming a shorter lag would be a fiction.
- **Folds:** expanding 3-fold, matching the 2026-09-10 walk-forward decision.
- **Benchmark:** buy-and-hold of the same cash.
- **Costs:** headline results are net of calibrated costs; recurring costs belong in the hurdle, and ATA rent is treated as a refundable lockup in the write-up.
- **Stopping rule:** Phase A, using this exact frozen protocol and no parameter grid, fails replication → stop.

All concrete protocol dates above are `TBD` deliberately. They will be filled only after the extractor has run and printed the actual available history. No backtest date range is invented in this record.

## Minimum-trades threshold

A wallet must have at least **10 DEX trade prints** in the training window to be rankable at all. I am choosing 10 here; the source material did not specify a number.

Why 10:

- The exact failure mode the rule exists to prevent is a wallet ranking on two lucky fills.
- With fewer than 10 prints, max drawdown is unstable and a single outlier can dominate the PnL/maxDD ratio.
- It is not a statistical guarantee. It is a floor that makes the ranking less obviously degenerate before the top-3 cap is applied.
- If fewer than 3 wallets meet the minimum threshold, Phase A is **inconclusive**, and the process stops rather than lowering the threshold to get a result.

## What was considered and rejected

- **Grid search over ranking metrics, or metric variants after a failed run:** rejected because it manufactures a winner from noise.
- **Unfreezing N, lag, fold structure, universe filters, or the benchmark after seeing results:** rejected for the same reason.
- **Using leaderboards or all-time-PnL-to-today lists as the universe:** rejected as survivorship bias with a UI.
- **Dropping unprofitable wallets at selection time:** rejected because performance-blind selection is the point of the universe method.
- **Sub-minute lag against 1m bars:** rejected as unachievable with current data resolution.
- **Fetching fills inside `generate()` or putting any model on the tick path:** rejected because it would break replayability; fills must be frozen and injected at construction.
- **Moving copy-trading to Open in the structural-edge inventory before Phase A has numbers:** rejected; the verdict stays Blocked with only a data-collection footnote.
- **Reopening directional prediction or live mode:** rejected; this decision changes neither the directional-prediction class closure nor `src/core/gate.py`.

## Reopening/abandonment condition

This decision is reopened, or the data-collection reopen is abandoned, on the following explicit condition:

- Phase A is run under the frozen protocol with the extractor-confirmed `TBD` dates filled in, and the result fails the replication gate:
  - net > 0 in at least 2 of 3 folds,
  - pooled net > 0,
  - no single fold contributing more than 60% of pooled net,
  - pooled trades at least 12.

If that happens, the data-collection reopen is closed and copy-trading returns to Blocked. The response is **not** to change the ranking metric, N, lag, universe filter, fold structure, or benchmark to search for a pass.

The only pre-result reason to update this record is that the extractor prints available history too short to construct a selection window, a later training window, and three folds. In that case the record is updated with a narrower feasible window or a determination that Phase A is infeasible, but the protocol constants remain unchanged.

This decision does not reopen directional prediction, and it does not unlock live mode.
