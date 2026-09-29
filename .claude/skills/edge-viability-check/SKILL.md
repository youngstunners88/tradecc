---
name: edge-viability-check
description: The mandatory first gate for ANY strategy hypothesis, directional or structural, before a backtest is written. Derives the edge size the hypothesis must deliver and checks it against real return distributions, the cost structure and sample constraints. Use whenever a new strategy idea is proposed, before pre-registration, before any harness is built, and whenever someone says "let's test whether X predicts Y". An afternoon of arithmetic comes before weeks of backtesting.
---

# Edge Viability Check

Four hypotheses on this project were tested correctly — pre-registered,
walk-forward, concentration-checked — and all four were unanswerable before the
first line of harness code was written. The edge they were hunting was smaller
than the measurement could resolve at $5–$10.

Nobody checked. The protocol had no step for it, because the protocol was
designed to stop you fooling yourself about a *result*, not to stop you
spending a month producing a result that could not mean anything.

This is that step. It runs **first**, and it is cheap: the whole thing is an
afternoon of arithmetic against data already on disk.

## Run it, don't just read it

As of 2026-09-19 this gate is a function, not only a document:

```bash
PYTHONPATH=src .venv/bin/python research/edge_gate.py --edge 0.5 --size 10
```

and an MCP server (`research/edge_gate_mcp.py`, tool
`tradecc_check_edge_viability`) so any session or tool can screen a claim in
one call. It reimplements nothing — it delegates to `research/trade_power.py`.

Steps 1-3 are decided automatically. **Step 4 is deliberately returned as
undecided**, because it needs real bars via `research/edge_budget.py`; a gate
that fabricated its hardest step would be worse than one that admits the gap.
A verdict of `INCOMPLETE` is not a pass.

## The gate

A hypothesis does not proceed to pre-registration until all four answer yes.

### 1. What edge does it claim, in gross % per round trip?

If the hypothesis cannot state a number, it is not ready. "It should be
profitable" is not an answer; "roughly 0.5–1% per round trip, because X" is.
An estimate with reasoning beats precision here — the gate is looking for
order of magnitude.

### 2. Does it clear the break-even hurdle at our size?

```bash
PYTHONPATH=src .venv/bin/python research/trade_power.py --size 10
```

Fixed cost is ~$0.0127 per round trip and does not scale down. At $5 an edge
below **0.254%** is negative after costs — not hard, *impossible*. At $10 the
hurdle is 0.127%.

**Below break-even, stop. No sample size fixes a negative expectancy.**

### 3. Is the edge large enough to be *detected* in the window we will run?

```bash
PYTHONPATH=src .venv/bin/python research/trade_power.py --size 10
```

A 1% gross edge is confirmable in ~9 round trips. A 0.2% edge needs ~1,332 —
19 months. The 30-day gate window resolves roughly 0.33–0.57% depending on
size.

**If the claimed edge sits under the floor for the window, the test cannot come
back trustworthy either way. Stop.** This is the step that would have saved the
four.

### 4. Does the price distribution actually contain that edge?

```bash
PYTHONPATH=src .venv/bin/python research/edge_budget.py --size 10 --cross-asset
```

For hypotheses whose payoff is a draw from the return distribution, this gives
the required direction accuracy per horizon. **Above ~60% is a red flag; above
70% is a refutation.** It also shows that volatility does not help — the noise
ratio (stdev ÷ E|move|) is near-invariant at 1.33–1.55, so trading something
wilder raises the available edge and the noise together.

For **structural** hypotheses — where profit comes from a mechanical situation
rather than predicting direction — step 4 does not apply directly, and steps
1–3 still do in full. Substitute: *how often does the situation occur, and what
does it pay when it does?* Frequency × payoff must clear steps 2 and 3. A
structural edge that fires twice a month cannot be validated in a 30-day window
whatever it pays.

## Before any of that

Check `.claude/skills/structural-edge-inventory` first. If the idea is already
in the ledger it is closed, and this gate is not the place to relitigate it.

## Who does the arithmetic

Steps 1 and 4 are the compute-heavy ones — estimating a claimed edge with
reasoning behind it, and deriving what the return distribution actually
contains. Route that drafting to `.claude/skills/openrouter-deepseek`
(`deepseek/deepseek-v4-pro` via OpenRouter): large context, flat pricing,
and it is good at long derivations.

What DeepSeek may do here:

- Draft the step-1 edge estimate and the reasoning behind the number.
- Draft the step-4 derivation, and verify a formula against how the concept
  is formally defined — the LuxAlgo reference in
  `planning/architecture/external-tools-registry.md` is there for exactly
  this lookup (reference only; not installed, not called from any execution
  path).
- Draft the four answers into the hypothesis's decision record.

What it may **not** do:

- **Produce the numbers that decide steps 2 and 3.** Those come from
  `research/trade_power.py` and `research/edge_budget.py`, run here, against
  data on disk. A model's arithmetic is a draft of a derivation, never a
  substitute for running the script — and a gate whose pass/fail came from a
  model is not a gate.
- Receive gate state, fingerprint data, wallet information or any secret.
  The cost structure and the price series are not secret; the bot's runtime
  state is, and none of it is needed to do this arithmetic.
- Deliver a verdict. DeepSeek drafts; Claude Code reviews and re-derives; the
  pass or fail is a human decision. Nothing the model outputs reaches a trade
  decision without that review step in between.

Any decision record carrying a DeepSeek-assisted derivation gets the
provenance note from that skill — DeepSeek-assisted, reviewed before
adoption, numeric claims re-derived independently, naming the script that
re-derived them.

## The two errors this check is prone to

Both were made while building it, both flattered the result, and both were
caught by re-deriving rather than re-reading:

1. **Using one detection floor across horizons.** Wrong — a longer hold yields
   fewer trades, so its floor is *higher*. Applying a single floor made an
   8-day hold look like it needed 53.6% accuracy, when it yields under four
   round trips a month and can confirm nothing at all.
2. **Mixing bases between the edge and the sample.** An oracle that skips
   losers has a different trade count than one that trades every window.
   Measuring the gross on one basis and the count on the other understates the
   trade and overstates the sample simultaneously.

When this check produces an encouraging answer, suspect it and re-derive. An
encouraging answer is exactly what a flattering error looks like.

## What a pass means

**Not that an edge exists.** Only that if one exists at the claimed size, the
measurement could see it. That is a permission to *test*, nothing more.

A fail is worth more than it looks: it is a month not spent, and it costs an
afternoon to obtain.

## Record the check

Whatever the outcome, write the four answers into the hypothesis's decision
record before pre-registration. A hypothesis that passed should show why; one
that failed should be findable, so the next session does not re-derive it.
