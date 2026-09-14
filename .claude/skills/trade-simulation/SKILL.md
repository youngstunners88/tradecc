---
name: trade-simulation
description: Exercise the full trade lifecycle against real recorded market data using research/replay_sim.py. Use when changing the paper loop, risk engine, cost model, fill simulator or strategy interface, when asking "does the machinery that places trades actually work", or when you need to know which code paths real data has never reached. NOT for deciding whether a strategy has an edge — that goes through the backtesting skill and walk-forward protocol.
---

# Trade Simulation

The 30-day paper run is the evidence the live gate rests on. Until it starts,
most of that machinery has only ever been exercised by unit tests against
fakes — and this repo has twice shipped a defect that every unit test passed
because the fake could not express it.

`research/replay_sim.py` replays recorded candles through the **real**
`PaperTrader`, one tick at a time: real strategy, real risk engine, real cost
model, real fill simulator, real session store.

```bash
PYTHONPATH=src .venv/bin/python research/replay_sim.py                    # 15m
PYTHONPATH=src .venv/bin/python research/replay_sim.py --interval 4h
```

## The one rule that matters

> **Trade count is a coverage measure, not a signal.**

This tool answers *"does the machinery work, and which branches has real data
reached?"*. It does **not** answer *"is this strategy any good?"*.

Concretely forbidden, because each is the selection bias the rest of the
protocol exists to prevent:

- Tuning parameters until the trade count or P&L rises. That is fitting to
  the replay window, and the window is the same data the strategy was built on.
- Quoting the replay's P&L as evidence for or against a strategy. It runs one
  window with no folds, no concentration check and no benchmark.
- Treating "more trades" as progress. A change that doubles trades has changed
  the strategy, which needs the pre-registration protocol, not this file.

Edge questions go through `research/walk_forward.py` and the `backtesting`
skill. The simulator's own output prints P&L **last** and says so, because
whatever is printed first is what gets quoted.

## What it is genuinely good for

**Finding paths real data never takes.** Every run prints
`BRANCHES REAL DATA NEVER REACHED`. As of 2026-09-14, across 15m/1h/4h/1d:

| Finding | Why it matters |
|---|---|
| `entry_blocked` reached on **no** interval | Risk rejection is unit-tested, but its *integration into the paper loop* has never run on real data |
| `stop_loss` fired **twice** in 58 exits, `take_profit` **once** | The two risk-driven exits — the ones that bound a loss — are nearly untouched by real data |
| **55 of 58** exits came from strategy signals | The exit path that is well-exercised is the one that is *not* a safety control |

None of that is visible from a backtest summary or from coverage percentages.
A line can be 100% covered by tests and still never have run on real input.

**Proving a refactor is behaviour-preserving.** The run is deterministic — no
network, no clock, no randomness — so identical cached data must produce an
identical report. A diff in the output after a refactor is a behaviour change,
and you should be able to name it.

**Point-in-time discipline is built in.** `ReplayCandleSource` serves bars
`0..i` at tick `i` and nothing after. A source handing over the full series
would let the strategy read its own future and turn the whole exercise into a
lookahead artefact.

## When to run it

- After any change to `paper/trader.py`, `risk/`, `execution/costs.py`,
  `execution/fills.py`, or a strategy's signal interface.
- Before merging anything that touches the money path.
- Alongside `research/stress_paper_loop.py`, which is the complement: this one
  uses real data and well-behaved providers, that one uses synthetic data and
  hostile providers. Both have found defects the other could not.

## Reporting what it found

Put lifecycle coverage first and P&L last, the way the tool does. If you
report a trade count, say in the same sentence that it measures coverage.
A number quoted without that qualifier will be read as performance by the
next person, including you in a month.
