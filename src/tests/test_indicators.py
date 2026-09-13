"""Indicators, checked against independently computed reference values.

The reference numbers here are derived from the published definitions, not
from this implementation's own output — a test that asserts whatever the
code already returns proves nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from strategy.indicators import ema, rsi, sma


def d(values) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


def test_sma_warms_up_then_averages():
    result = sma(d([1, 2, 3, 4, 5]), 3)

    assert result[:2] == [None, None]
    assert result[2] == Decimal(2)
    assert result[3] == Decimal(3)
    assert result[4] == Decimal(4)


def test_sma_is_exact_with_awkward_decimals():
    result = sma(d(["0.1", "0.2", "0.3"]), 3)

    # Floats would give 0.20000000000000004 here.
    assert result[2] == Decimal("0.2")


def test_ema_seeds_with_the_sma_of_the_first_window():
    values = d([1, 2, 3, 4, 5])

    result = ema(values, 3)

    assert result[:2] == [None, None]
    assert result[2] == Decimal(2)  # SMA of 1,2,3


def test_ema_applies_the_standard_multiplier():
    result = ema(d([1, 2, 3, 4, 5]), 3)

    # k = 2/(3+1) = 0.5; next = (4 - 2) * 0.5 + 2 = 3
    assert result[3] == Decimal(3)
    # next = (5 - 3) * 0.5 + 3 = 4
    assert result[4] == Decimal(4)


def test_ema_reacts_faster_than_sma_to_a_jump():
    values = d([10] * 10 + [20])

    assert ema(values, 5)[-1] > sma(values, 5)[-1]


def test_ema_returns_all_none_when_series_too_short():
    assert ema(d([1, 2]), 5) == [None] * 2


def test_ema_output_is_aligned_to_input_length():
    """Misaligned indicators are how look-ahead bias creeps in."""
    values = d(range(30))

    assert len(ema(values, 12)) == len(values)
    assert len(rsi(values, 14)) == len(values)


def test_rsi_is_100_for_an_unbroken_rally():
    result = rsi(d(range(1, 20)), 14)

    assert result[-1] == Decimal(100)


def test_rsi_is_0_for_an_unbroken_selloff():
    result = rsi(d(range(30, 10, -1)), 14)

    assert result[-1] == Decimal(0)


def test_rsi_is_50_for_a_flat_series():
    """No gains and no losses is neutral, not a division by zero."""
    result = rsi(d([100] * 20), 14)

    assert result[-1] == Decimal(50)


def test_rsi_warmup_is_one_longer_than_the_period():
    """RSI needs `period` *changes*, which needs period+1 observations."""
    result = rsi(d(range(1, 20)), 14)

    assert result[13] is None
    assert result[14] is not None


def test_rsi_matches_a_hand_computed_wilder_value():
    # Alternating +2 / -1 changes: over the first 14 changes there are
    # 7 gains of 2 and 7 losses of 1.
    values = [Decimal(100)]
    for i in range(14):
        values.append(values[-1] + (Decimal(2) if i % 2 == 0 else Decimal(-1)))

    result = rsi(values, 14)

    avg_gain = Decimal(14) / Decimal(14)  # 7 gains of 2 -> 14/14 = 1
    avg_loss = Decimal(7) / Decimal(14)  # 7 losses of 1 -> 7/14 = 0.5
    expected = Decimal(100) - (Decimal(100) / (Decimal(1) + avg_gain / avg_loss))

    assert result[14] == expected


def test_rsi_falls_when_losses_arrive():
    rising = d(list(range(1, 20)))
    then_falling = rising + d([18, 16, 14, 12, 10])

    assert rsi(then_falling, 14)[-1] < rsi(rising, 14)[-1]


def test_rsi_stays_within_bounds():
    values = d([10, 12, 11, 15, 14, 18, 13, 20, 19, 25, 22, 30, 28, 35, 31, 40])

    for value in rsi(values, 5):
        if value is not None:
            assert Decimal(0) <= value <= Decimal(100)


@pytest.mark.parametrize("period", [0, -1])
def test_rejects_invalid_periods(period):
    for fn in (sma, ema, rsi):
        with pytest.raises(ValueError, match="period"):
            fn(d([1, 2, 3]), period)


def test_empty_series_returns_empty():
    assert ema([], 3) == []
    assert rsi([], 3) == []
