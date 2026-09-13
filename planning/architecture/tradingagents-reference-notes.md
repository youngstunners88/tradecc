# Reference Notes: TradingAgents (TauricResearch) → informs `astra-analyst`

Not a dependency. Nothing here is installed or run. This is a pattern
reference for whoever builds the `astra-analyst` skill under v0.2 —
read this before designing that skill's control flow.

## Why this is worth reading
TradingAgents is a credible, actively maintained (80k+ stars), academic-
grounded multi-agent LLM trading framework. Its own maintainers
explicitly recommend against using it with real money — it's a research
tool. That caveat is exactly why it's useful here: it's a mature example
of the "LLM proposes, something else disposes" pattern `astra-analyst`
is meant to follow, built by people who've already hit the failure modes
we'd otherwise discover the hard way.

## The structural pattern worth borrowing
Three layers, not one model making a call:
1. **Analyst team** — specialized agents (fundamental, sentiment, news,
   technical) each produce a narrow report. No single agent sees the
   whole picture or makes a decision.
2. **Researcher team** — a bullish and a bearish agent explicitly debate
   the analyst reports. This forces the system to weigh opposing
   interpretations rather than defaulting to whichever read came first.
3. **Trading team** — a trader agent synthesizes the debate, but a risk
   manager and portfolio manager must approve before anything is
   treated as a decision.

Applied to `astra-analyst`: the LLM layer should produce a *report* or
*flag*, never a `TradeIntent` directly. The existing `RiskEngine.approve()`
gate — already built, already tested — plays the role of the risk
manager/portfolio manager step here. Nothing changes about
`RiskEngine`; the LLM output has to earn its way through the same gate
every other signal source does.

## The bug class worth checking our own code for
TradingAgents' 2026 releases specifically fixed **look-ahead / point-in-
time bias** across their macro, sentiment, and decision-log data —
i.e., their backtests were at some point accidentally using information
that wouldn't have been available at the time of the simulated decision.
This is a classic and easy-to-introduce bug in any backtest harness.

**Action item, not yet done:** audit `research/walk_forward.py` and the
core backtest runner for the same bug class — specifically, confirm
that indicator warmup, candle boundaries, and any external data
(prices, wallet history, if copy-trading ever reads it) are all
strictly bounded to information available at or before the simulated
decision timestamp, never after.

## What NOT to borrow
- Do not adopt real-money usage — their own team advises against it,
  and nothing in this project changes that advice.
- Do not adopt their broad multi-provider model catalog approach as a
  reason to add LLM dependencies beyond what `astra-analyst` needs.
- Do not treat "reads financial news/social sentiment" as something
  TradeCC needs immediately — that's scope for `market-intelligence`
  and `astra-analyst` to define deliberately, not to inherit wholesale
  from a stock-market-focused framework.
