---
name: repo-intake
description: How to evaluate a third-party trading repo, tool, MCP or "AI trading" recommendation before adopting it. Use whenever a new repo, library, data provider, MCP server or YouTube/newsletter/Twitter recommendation arrives and the question is "should we use this?" — especially when it arrives with enthusiasm, star counts, or a claim about alpha.
---

# Repo intake

Trading tools arrive with a recommender attached, and the recommender is
almost never the author. The author usually writes a careful README with a
disclaimer; by the time it reaches you it has become "this turns Claude into
a hedge fund." **Read the repo before the recommendation.**

This is the checklist. It is short on purpose — it should cost twenty minutes,
not an afternoon.

## 1. Verify the claims against the repo itself

Never repeat a figure from the recommender. Open the repo and check:

- **Star count** — and then ignore it. Stars measure how many people liked an
  idea. That is precisely the quantity that says nothing about whether an edge
  survives costs and sampling. A 63.5k-star repo in this project's own review
  turned out to disclaim all profitability.
- **The repo's own disclaimer.** This is the highest-signal paragraph in any
  trading repo and the first thing stripped in transit. "For educational
  purposes only", "does not actually make any trades", "no investment advice"
  — if the author says it, the author means it.
- **Any profitability or backtest claim.** Usually there is none. Note that
  explicitly, because its absence is the answer to "does this have edge?"
- **The licence.** AGPL-3.0 in particular: this project has reviewed §13's
  network-provision clause twice now (PineTS, OpenBB) and it is the real
  forward risk for a bot that might ever expose a dashboard.

## 2. Ask which binding constraint it touches

`CLAUDE.md`: **the binding constraints are position size and data access, not
the code.** So:

- Does it change the **fixed cost per round trip**? Almost nothing does.
- Does it change **σ/μ** or the **detection floor**? Almost nothing does.
- Does it change **data access** — and if so, on which axis? Breadth is not
  the same as point-in-time cleanliness. What blocks copy-trading and pump.fun
  is PIT-clean history, not more providers. Aggregating more current-snapshot
  sources does not produce PIT-clean data, and assuming it does is the
  look-ahead trap this repo has already audited for once.
- Does it change **venue reachability**? (Funding carry needs a perps venue.)

If the honest answer to all four is no, it is **capability, not edge**. That
is not a reason to reject it — a nicer chart is a nicer chart — but it must
not be logged as progress toward an edge.

## 3. Run any actual claim through the gate

If the tool or its recommender makes a *strategy* claim, it goes through the
same two gates as any idea of our own, in this order:

```bash
PYTHONPATH=src .venv/bin/python research/edge_inventory.py --idea "..."
PYTHONPATH=src .venv/bin/python research/edge_gate.py --edge 0.5 --size 10
```

or the MCP tools `tradecc_check_inventory` then
`tradecc_check_edge_viability`.

**Most third-party claims fail at step 1 of the viability gate** — they state
no gross edge per round trip. That is the correct outcome, not a technicality,
and it is fast.

## 4. Check the execution-safety surface specifically

For anything that can place an order, or that an LLM can configure:

- **How far is it from live?** If paper→live is one boolean in a config file
  an agent can edit, say so out loud. That was true of the Alpaca MCP
  (`ALPACA_PAPER_TRADE: "false"`), and against rule 5 it is a risk surface,
  not a convenience.
- **What keys does it want, and does it need them at all?**
- **Does it add a runtime, a daemon, or a second HTTP stack?** This project
  has no third-party HTTP dependency by choice.

## 5. Write the verdict where the next person will look

`planning/architecture/external-tools-registry.md`, in the right section:
ADOPTED / EVALUATING / REJECTED / PARKED / NOT ADOPTED. With the *reason*, not
just the verdict — the registry's value is that a future session can check the
reasoning instead of re-deriving it or, worse, re-adopting the thing.

A verdict nobody can find is a verdict that gets paid for twice.

## The failure mode this exists to prevent

Adopting capability and recording it as edge. Seven repos were reviewed on
2026-09-19 (`planning/architecture/2026-09-19-ai-trading-repo-review.md`);
five were pure capability, one was scope-mismatched, and the one that touched
a real constraint touched the wrong axis of it. The nutritious output of that
review was not a repo — it was noticing that none of them could have been
screened quickly, which is why the gate is now callable.

Expect that ratio again. It is not cynicism; it is what the arithmetic
predicts when the binding constraint is size and data rather than tooling.
