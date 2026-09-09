# Decision: Tuning / Held-Out Split for Parameter Exploration (2026-09-09)

## Context
The first backtests showed the momentum strategy is gross profitable and
net unprofitable at $10 sizes (1h: net −$0.12; 15m: net −$2.59). Before
any parameter exploration begins, the evaluation protocol is fixed here so
it cannot quietly become "tune until the validation number looks good."

**This record is written before a single parameter has been changed.** The
only thing inspected beforehand was how much history each interval has —
which is a property of the data source, not of any strategy result.

## The split

**Rule (fixed in advance):** for each eligible interval, the first **70%**
of available candles is the tuning range and the last **30%** is held out.
The split is chronological — never random — because random splits leak
future information into the tuning set through overlapping indicator
windows and market regime.

Boundaries, computed from the data as it stood on 2026-09-09:

| Interval | Candles | Tuning range | Held-out range | First held-out candle |
|---|---|---|---|---|
| 1h | 1000 | 2026-07-29 → 2026-08-28 (700) | 2026-08-28 → 2026-09-09 (300) | `2026-08-28T03:00:00+00:00` |
| 4h | 1000 | 2026-03-27 → 2026-07-21 (700) | 2026-07-21 → 2026-09-09 (300) | `2026-07-21T16:00:00+00:00` |
| 1d | 184 | 2026-03-10 → 2026-07-15 (128) | 2026-07-16 → 2026-09-09 (56) | `2026-07-16T00:00:00+00:00` |

**Excluded: 15m.** Only ~10 days of history exists at that interval, and a
70/30 split of it leaves roughly 7 days to tune on and 3 to validate
against. That is not enough to distinguish a strategy from noise, and
including it would mostly add opportunities to get lucky.

**1d is included with a caveat:** 128 tuning candles after indicator
warmup leaves few decision bars and therefore few trades. Results there
should be read as weak evidence regardless of sign.

## Protocol

1. Sweep parameters **on the tuning range only**. The held-out range is
   not loaded, scored, or looked at during this phase.
2. **Selection rule, fixed in advance:** the winner per interval is the
   configuration with the highest **net** expectancy per trade on the
   tuning range, subject to a minimum of **10 closed trades**. The trade
   minimum exists so a single lucky trade cannot win the sweep.
3. Evaluate **exactly one** configuration per interval — the tuning
   winner — on the held-out range. One shot, no re-picking.
4. Report the held-out numbers whatever they say.

## Search grid (fixed in advance)

- `fast_ema`: 5, 8, 12, 20
- `slow_ema`: 21, 26, 34, 50
- `rsi_period`: 7, 14, 21
- `rsi_overbought`: 60, 70, 80
- Intervals: 1h, 4h, 1d

Combinations where `fast_ema >= slow_ema` are invalid and skipped. All
other risk and cost settings stay at their defaults: **position size
$10**, slippage cap 0.5%, stop-loss 5%, take-profit 10%.

## Stopping rule (the part that matters)

If the held-out result shows **no net edge at $10** after this sweep, the
answer is to say so plainly and stop — not to widen the grid, add
indicators, or search for a range where it works. Each of those is a way
of fitting the validation data by hand.

At that point the indicated next step, per the project's own cost
analysis, is **testing a larger position size**, not further tuning:
fixed costs (base fee, priority fee, ATA rent) do not scale with trade
size, so at $10 they dominate regardless of which parameters are chosen.
Raising position size is a decision for the user, requires the explicit
`position_size_override_ack` in config (CLAUDE.md rule 6), and is not
something this exploration may do on its own.

## What this record forecloses
- Changing the split after seeing results.
- Evaluating more than one configuration per interval on held-out data.
- Reporting a tuning-range number as though it were validation evidence.
- Treating a positive held-out result as clearing the live gate: the gate
  additionally requires 30 days of paper trading and a max-drawdown
  threshold set beforehand. A good backtest is necessary, not sufficient.
