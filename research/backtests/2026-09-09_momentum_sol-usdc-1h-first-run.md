# Backtest — momentum on So11111111111111111111111111111111111111112

## Verdict

**Net P&L: -0.1183 USD** over 15 trades (expectancy -0.0079 USD/trade).

> Net expectancy is not positive. This strategy/parameter set does not clear the validation gate.

## Run parameters

| Field | Value |
|---|---|
| Strategy | `momentum` |
| Token | `So11111111111111111111111111111111111111112` |
| Data source | GeckoTerminal |
| Candle interval | 1h |
| Date range | 2026-07-29T23:00:00+00:00 → 2026-09-09T14:00:00+00:00 |
| Candles | 1000 |
| Initial capital | 100.0000 USD |
| `fast_ema` | 12 |
| `rsi_overbought` | 70 |
| `rsi_oversold` | 30 |
| `rsi_period` | 14 |
| `slow_ema` | 26 |

## Results

| Metric | Value |
|---|---|
| **Net P&L (after fees & slippage)** | **-0.1183 USD** |
| Gross P&L | 0.3195 USD |
| Total fees & costs | 0.4379 USD |
| Cost drag (fees ÷ \|gross\|) | 137.03% |
| Expectancy per trade (net) | -0.0079 USD |
| Trades | 15 |
| Win rate (net of costs) | 40.00% |
| Max drawdown | 1.24% |
| Final equity | 99.8817 USD |

## Execution detail

| Metric | Value |
|---|---|
| Signals evaluated | 974 |
| Entries blocked by risk | 0 |
| Position open at end | yes |

## Trades

| # | Entry | Exit | Entry px | Exit px | Gross | Fees | Net | Reason |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-08-02T05:00:00+00:00 | 2026-08-03T06:00:00+00:00 | 73.9427 | 72.4533 | -0.2014 | 0.4099 | -0.6113 | `ema_cross_down` |
| 2 | 2026-08-03T15:00:00+00:00 | 2026-08-06T03:00:00+00:00 | 73.8602 | 73.2004 | -0.0893 | 0.0020 | -0.0913 | `ema_cross_down` |
| 3 | 2026-08-07T12:00:00+00:00 | 2026-08-08T11:00:00+00:00 | 74.0676 | 75.2181 | 0.1553 | 0.0020 | 0.1533 | `rsi_overbought` |
| 4 | 2026-08-12T00:00:00+00:00 | 2026-08-12T16:00:00+00:00 | 76.5142 | 75.2781 | -0.1616 | 0.0020 | -0.1636 | `ema_cross_down` |
| 5 | 2026-08-13T05:00:00+00:00 | 2026-08-13T15:00:00+00:00 | 76.6477 | 75.4116 | -0.1613 | 0.0020 | -0.1633 | `ema_cross_down` |
| 6 | 2026-08-13T23:00:00+00:00 | 2026-08-14T03:00:00+00:00 | 76.3412 | 75.3693 | -0.1273 | 0.0020 | -0.1293 | `ema_cross_down` |
| 7 | 2026-08-15T17:00:00+00:00 | 2026-08-16T05:00:00+00:00 | 75.9267 | 74.9956 | -0.1226 | 0.0020 | -0.1246 | `ema_cross_down` |
| 8 | 2026-08-16T06:00:00+00:00 | 2026-08-16T08:00:00+00:00 | 75.8576 | 75.0611 | -0.1050 | 0.0020 | -0.1070 | `ema_cross_down` |
| 9 | 2026-08-17T06:00:00+00:00 | 2026-08-19T12:00:00+00:00 | 76.1274 | 78.1030 | 0.2595 | 0.0020 | 0.2575 | `rsi_overbought` |
| 10 | 2026-08-23T11:00:00+00:00 | 2026-08-24T07:00:00+00:00 | 95.2688 | 93.6482 | -0.1701 | 0.0020 | -0.1721 | `ema_cross_down` |
| 11 | 2026-08-24T10:00:00+00:00 | 2026-08-25T00:00:00+00:00 | 95.1316 | 101.8889 | 0.7103 | 0.0020 | 0.7083 | `rsi_overbought` |
| 12 | 2026-08-26T22:00:00+00:00 | 2026-08-26T23:00:00+00:00 | 100.0244 | 102.1832 | 0.2158 | 0.0020 | 0.2138 | `rsi_overbought` |
| 13 | 2026-08-29T18:00:00+00:00 | 2026-08-30T23:00:00+00:00 | 105.5417 | 101.6349 | -0.3702 | 0.0020 | -0.3722 | `ema_cross_down` |
| 14 | 2026-09-03T02:00:00+00:00 | 2026-09-03T14:00:00+00:00 | 101.4519 | 103.9604 | 0.2473 | 0.0020 | 0.2453 | `rsi_overbought` |
| 15 | 2026-09-05T12:00:00+00:00 | 2026-09-06T03:00:00+00:00 | 103.3244 | 105.8048 | 0.2401 | 0.0020 | 0.2381 | `rsi_overbought` |

## Caveats

- Slippage is **assumed**, not measured: historical candles carry no quotes. See `BacktestConfig.assumed_slippage_pct`.
- Fills are modelled at the adverse side of the assumed slippage on both entry and exit.
- A single backtest over one date range is weak evidence. Note why this range was chosen, and do not tune parameters on the same data used to evaluate them.

## Notes

First end-to-end run of the Stage 4 pipeline against live GeckoTerminal data. Range is simply the most recent 1000 hourly candles available, not chosen for favourability. ATA rent is charged once per mint, not per trade.
