# Replay coverage across real cached data — 2026-09-14

First run of `research/replay_sim.py`: recorded candles driven through the
**real** `PaperTrader` tick by tick, at four intervals.

**This is a coverage report, not a performance report.** Trade counts below
measure how much of the machinery real data exercised. They are not evidence
about the strategy, and the P&L column exists only because omitting it would
look like concealment — momentum remains closed per
`planning/decisions/2026-09-12-kill-ema-rsi-momentum.md`.

| Interval | Ticks | Entered | Exited | Net $ (corrected) | Net $ (as first published) | Branches never reached |
|---|---|---|---|---|---|---|
| 15m | 940 | 22 | 22 | **−1.9855** | −1.1097 | `entry_blocked` |
| 1h | 940 | 16 | 15 | **−0.0596** | +0.5426 | `entry_blocked` |
| 4h | 940 | 20 | 19 | **+0.1671** | +0.9307 | `entry_blocked` |
| 1d | 124 | 2 | 2 | **+0.9054** | +0.9899 | `entry_blocked` |

> **Correction, 2026-09-14.** The right-hand column was measured before the
> SELL-slippage fix landed on `main`. `MockQuoteSource` applied BUY-direction
> slippage to both sides, so every simulated exit filled *better* than it
> should have and all four figures were optimistic. Every corrected number
> moved in the pessimistic direction, and 1h crossed from positive to negative
> — which is exactly the magnitude of error the fix was for.
>
> **The coverage findings below are unaffected.** They depend on which branches
> execute, not on what the fills were worth.

## The findings that matter

**1. `entry_blocked` was reached on no interval.** Every risk control is
unit-tested, but the *integration of a rejection into the paper loop* has never
run against real data. The path exists, is covered by tests, and has never
executed on a real bar.

**2. The risk-driven exits are nearly untouched.** Across all four intervals:

| Exit reason | Count |
|---|---|
| `ema_cross_down` | 39 |
| `rsi_overbought` | 16 |
| `stop_loss` | **2** |
| `take_profit` | **1** |

**55 of 58 exits came from strategy signals.** The two exits that *bound a
loss* fired three times in total, and `take_profit` only on the 1d series.
So the well-exercised exit path is the one that is not a safety control, and
the ones that are have almost no real-data mileage behind them.

This is invisible from a backtest summary and from coverage percentages alike:
those lines are 100% covered by unit tests. Coverage tooling measures whether a
line ran, not whether it ran on input that could have been wrong.

**3. The lifecycle itself works end to end on real data** — 60 entries and 58
exits across the four runs, with fills, fees, session persistence and risk
approval all on the real path. That was not previously demonstrated outside
unit tests against fakes, which is exactly where the two unit-mismatch defects
in `failure-modes` Shape B hid.

## What was NOT concluded

- Nothing about edge. One window, no folds, no concentration check, no
  benchmark. The sign of the P&L column flips across intervals, which is
  itself a reason not to read it.
- No parameter was changed, and none may be changed to raise the trade count.
  That is fitting to the replay window.

## Follow-up worth considering (not started)

The `entry_blocked` gap is a real hole in the evidence: a risk rejection has
never been observed to flow through the paper loop on real data. Closing it
needs either a replay window containing a genuine rejection, or an explicit
fault-injection mode in the simulator. Either is a decision, not a tweak, and
neither is started here.
