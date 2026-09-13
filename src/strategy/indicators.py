"""Technical indicators, in Decimal.

Hand-rolled rather than taken from pandas/pandas-ta, for two reasons that
matter to this project specifically:

1. **Exactness.** pandas computes in float64. Every other number in this
   codebase is Decimal, and a signal that depends on float rounding is a
   signal that can differ between a backtest and the live run that is
   supposed to reproduce it.
2. **Reproducibility.** These are short, well-defined recurrences with
   published reference values, so they can be tested against known-good
   numbers rather than trusted. That is worth more here than a
   dependency.

pandas remains a reasonable choice for Stage 4 *analysis and reporting*
over results; it is the signal path specifically that stays exact.

Every function returns a list aligned to its input, with `None` for
positions where there is not yet enough history. Returning a shorter list
would silently misalign indicators against candles, which is the classic
way look-ahead bias creeps in.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

HUNDRED = Decimal(100)


def sma(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    """Simple moving average."""
    _validate_period(period)
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out
    window = sum(values[:period], Decimal(0))
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def ema(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    """Exponential moving average, seeded with the SMA of the first window.

    Seeding with an SMA (rather than the first value) is the convention
    charting platforms use; seeding differently shifts every subsequent
    value and would make our signals disagree with any external chart.
    """
    _validate_period(period)
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out

    multiplier = Decimal(2) / Decimal(period + 1)
    previous = sum(values[:period], Decimal(0)) / period
    out[period - 1] = previous

    for i in range(period, len(values)):
        previous = (values[i] - previous) * multiplier + previous
        out[i] = previous
    return out


def rsi(values: Sequence[Decimal], period: int = 14) -> list[Decimal | None]:
    """Relative Strength Index using Wilder's smoothing.

    Wilder's smoothing, not a simple average of the last `period` changes —
    the two diverge quickly, and Wilder's is what "RSI(14)" means
    everywhere it is quoted.
    """
    _validate_period(period)
    out: list[Decimal | None] = [None] * len(values)
    if len(values) <= period:
        return out

    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for previous, current in zip(values, values[1:]):
        change = current - previous
        gains.append(max(change, Decimal(0)))
        losses.append(max(-change, Decimal(0)))

    avg_gain = sum(gains[:period], Decimal(0)) / period
    avg_loss = sum(losses[:period], Decimal(0)) / period
    out[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    # An unbroken run of gains has no downside to divide by. RSI is 100 by
    # definition there, not an error.
    if avg_loss == 0:
        return HUNDRED if avg_gain > 0 else Decimal(50)
    rs = avg_gain / avg_loss
    return HUNDRED - (HUNDRED / (Decimal(1) + rs))


def _validate_period(period: int) -> None:
    if period < 1:
        raise ValueError("period must be at least 1")
