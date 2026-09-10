# Decision: v0.2 Intelligence Architecture (2026-09-10)

## Context

v0.1 is complete through Stage 5 and its verdict is negative: the
momentum strategy showed **no net edge at $10 on held-out data**
(`research/backtests/2026-09-09_momentum_parameter-sweep-holdout.md`).
Per the stopping rule fixed in advance, parameter search stopped.

The user has now greenlit v0.2 with three additions: a live market-data
layer ("eyes and ears"), copy-trading, and GPT-6 Astra as a research
participant. This record fixes the architecture **before** any of it is
built, because each addition expands what the bot can act on and two of
them expand what can go wrong.

## What is greenlit

| Capability | Status change |
|---|---|
| Copy-trading / wallet-following | Deferred → **greenlit** |
| Web research tools (Firecrawl et al.) | Gated → **unlocked for wallet vetting** |
| LLM (Astra) research + veto authority | v0.1 forbidden → **permitted under limits below** |
| Live market-data layer | New |
| Regime detection | New |

`CLAUDE.md`'s seven non-negotiable rules are unchanged and continue to
override everything here.

## The governing principle: asymmetric authority

Every new component in v0.2 is granted **refusal authority only.** New
inputs may cause a trade not to happen. No new input may cause a trade to
happen.

The reasoning is an expected-cost argument, not a stylistic preference:

- A wrong refusal costs one missed opportunity — bounded, and at $10
  sizes against ~0.6% round-trip slippage, often not a loss at all.
- A wrong entry costs capital, and correlated wrong entries are precisely
  what the daily circuit breaker exists to contain.

Applied per component:

- **Market data** may veto on stale prices, thin liquidity, or price
  impact exceeding expected edge. It does not generate signals.
- **Regime detection** may suppress a signal the strategy proposed. It
  cannot originate one.
- **Astra** may research, score candidates offline, and raise flags. It
  cannot emit a trade.
- **Copy-trading** is the one exception that originates signals — and it
  originates a `TradeIntent` that goes through `RiskEngine.approve()`
  unchanged, exactly like an EMA crossover. It is a new signal source
  under existing controls, not a new authority.

A useful consequence: since Astra's maximum authority is refusal, a
successful prompt injection through untrusted token metadata degrades to
a missed trade rather than a capital loss.

## LLM boundary: propose, then dispose

The v0.1 rule — no LLM in the trade-decision path — existed because model
calls are non-deterministic and silently versioned, which makes backtests
meaningless. That reasoning is undamaged, so the rule is refined rather
than repealed:

> **Astra proposes. Deterministic Python disposes.**

Astra may propose features, thresholds, regime definitions, and wallet
assessments. Before any proposal affects trading it is **frozen into
deterministic code** and validated under the anti-overfit protocol. The
frozen code runs identically in backtest, paper, and live. No runtime
model call sits in the signal path.

All model output that touches a decision is **structured and schema-
validated**; a validation failure is a refusal, not something to
re-prompt until it parses. Model ID and prompt hash are logged with every
assessment.

## Validation discipline carries over unchanged

The failure mode that invalidated the sweep — taking the maximum of a
mostly-negative distribution — recurs in both new capabilities, and in
copy-trading it recurs at far larger N.

1. **The 2026-09-09 held-out slice is spent.** It has been scored; it is
   no longer out-of-sample for anything. New work uses genuinely new
   history or walk-forward folds with **every fold reported**, not the
   best one.
2. **Wallet selection follows the same protocol as parameter selection.**
   Candidates are chosen on history up to a cutoff T fixed in advance and
   evaluated on post-T behaviour, one shot, no re-picking. Selection-pool
   size is recorded, because "best of 10,000" and "best of 12" are
   different claims.
3. **Trade counts are reported beside every result.** The sweep's
   "+$0.47 on 3 trades" is the standing example of a number that looks
   like evidence and is not.
4. **Every new threshold is a parameter** and counts against the search
   budget. A filter with a tuned cutoff is not free.
5. **A decision record precedes each search**, per
   `2026-09-09-tuning-holdout-split.md`.

## The live gate is unchanged and does not fork

Copy-trading does **not** inherit momentum's validation and does not get
a parallel gate. Any strategy reaching live requires 30 days of paper
trading, positive net expectancy after costs, a max-drawdown threshold
set before the run started, and explicit human sign-off. `core/gate.py`
is untouched by this record.

## Build order

Ordered by expected value per unit of risk, which puts the cheapest real
improvement first:

1. **Measured cost, replacing assumed cost.** Use Jupiter's
   `priceImpactPct` per trade instead of `assumed_slippage_pct`, and
   source `sol_price_usd` live — it is hardcoded to `200` while SOL
   traded at ~$102 on 2026-09-10, overstating SOL-denominated costs by
   nearly 2×. This also absorbs the outstanding correction from the sweep
   write-up (priority fees modelled as a flat total rather than per
   compute unit; Jito tips not modelled at all).
2. **Liquidity and data-validity gating.** Refuse trades that cannot be
   priced honestly.
3. **The regime mechanism check.** At *default* parameters, compare
   expectancy in trend-labelled versus chop-labelled windows. Cheap,
   fast, and it tests the hypothesis before any tuning. Be prepared for
   it to say no.
4. **Copy-trading discovery and vetting**, offline, written up in
   `research/wallet-tracking/` before any execution is built.
5. **Astra wired to (4)** as batch analysis.

Steps 1 and 2 improve net P&L mechanically by removing negative-
expectancy trades. They do not require finding an edge, which is why they
come first.

## What this record forecloses

- Any runtime LLM call in the signal path.
- Any component granted authority to originate a trade outside
  `RiskEngine.approve()`.
- Re-scoring the spent 2026-09-09 held-out slice as though it were
  out-of-sample.
- Building copy-trading execution against a wallet with no write-up in
  `research/wallet-tracking/`.
- Treating a positive backtest as gate-clearing. It is necessary, never
  sufficient.

## Honest expectation

None of this guarantees profitability, and the evidence so far points the
other way. What steps 1–2 reliably do is stop the bot taking trades that
were negative-expectancy before the price moved. Steps 3–5 are
hypotheses, held to the same standard that has already rejected one
strategy — and the correct outcome for a hypothesis that fails validation
remains a write-up in `research/` and a stop, not a wider search.
