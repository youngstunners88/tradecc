"""Momentum strategy — signal generation on known price series."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.config import StrategyConfig
from core.types import Candle, SignalType
from strategy.base import Strategy
from strategy.registry import available_strategies, build_strategy
from strategy.strategy_momentum import MomentumParams, MomentumStrategy

TOKEN = "So11111111111111111111111111111111111111112"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def candles(prices) -> list[Candle]:
    return [
        Candle(
            timestamp=START + timedelta(minutes=15 * i),
            open=Decimal(str(p)),
            high=Decimal(str(p)),
            low=Decimal(str(p)),
            close=Decimal(str(p)),
            volume=Decimal("1000"),
        )
        for i, p in enumerate(prices)
    ]


@pytest.fixture
def strategy() -> MomentumStrategy:
    # Short periods so test series stay readable.
    return MomentumStrategy(
        MomentumParams(fast_ema=3, slow_ema=6, rsi_period=5, rsi_overbought=Decimal("70"))
    )


def test_hold_when_history_is_too_short(strategy):
    signal = strategy.generate(TOKEN, candles([1, 2, 3]))

    assert signal.type is SignalType.HOLD
    assert signal.metadata["reason"] == "insufficient_history"


def test_never_signals_before_minimum_candles(strategy):
    """A signal on thin history is a signal from noise."""
    for count in range(1, strategy.minimum_candles):
        signal = strategy.generate(TOKEN, candles(list(range(1, count + 1))))
        assert signal.type is SignalType.HOLD


def test_empty_series_raises(strategy):
    with pytest.raises(ValueError, match="empty"):
        strategy.generate(TOKEN, [])


def test_buy_on_upward_crossover(strategy):
    # Decline, then a recovery that pulls the fast EMA back through the slow.
    prices = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96]

    signal = strategy.generate(TOKEN, candles(prices))

    assert signal.type is SignalType.BUY
    assert signal.metadata["reason"] == "ema_cross_up"


def test_sell_on_downward_crossover(strategy):
    prices = [80, 82, 84, 86, 88, 90, 92, 94, 92, 88, 84]

    signal = strategy.generate(TOKEN, candles(prices))

    assert signal.type is SignalType.SELL
    assert signal.metadata["reason"] == "ema_cross_down"


def test_downward_cross_fires_once_not_every_bar(strategy):
    """The bars after a cross stay HOLD even though fast is still below slow."""
    prices = [80, 82, 84, 86, 88, 90, 92, 94, 92, 88, 84]

    assert strategy.generate(TOKEN, candles(prices)).type is SignalType.SELL
    for extra in ([80], [80, 76]):
        later = strategy.generate(TOKEN, candles(prices + extra))
        assert later.type is SignalType.HOLD
        assert later.metadata["reason"] == "no_crossover"


def test_hold_while_a_trend_merely_continues(strategy):
    """A crossover is an event. Acting on the state re-enters every bar."""
    prices = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 100, 104, 108]

    signal = strategy.generate(TOKEN, candles(prices))

    assert signal.type is not SignalType.BUY


def test_overbought_rsi_sells_even_without_a_crossover(strategy):
    prices = [10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]

    signal = strategy.generate(TOKEN, candles(prices))

    assert signal.type is SignalType.SELL
    assert signal.metadata["reason"] == "rsi_overbought"


def test_rsi_filter_blocks_a_buy_at_an_exhausted_top():
    """A bare crossover would buy here; the RSI filter is why we do not."""
    permissive = MomentumStrategy(
        MomentumParams(fast_ema=3, slow_ema=6, rsi_period=5, rsi_overbought=Decimal("99"))
    )
    filtered = MomentumStrategy(
        MomentumParams(fast_ema=3, slow_ema=6, rsi_period=5, rsi_overbought=Decimal("60"))
    )
    prices = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96]
    series = candles(prices)

    assert permissive.generate(TOKEN, series).type is SignalType.BUY
    assert filtered.generate(TOKEN, series).type is not SignalType.BUY


def test_signal_carries_indicator_values(strategy):
    prices = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96]

    signal = strategy.generate(TOKEN, candles(prices))

    assert Decimal(signal.metadata["fast_ema"]) > 0
    assert Decimal(signal.metadata["slow_ema"]) > 0
    assert Decimal(signal.metadata["rsi"]) >= 0


def test_signal_timestamp_is_the_candle_not_the_wall_clock(strategy):
    series = candles([100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96])

    signal = strategy.generate(TOKEN, series)

    assert signal.timestamp == series[-1].timestamp
    assert signal.price == series[-1].close


def test_is_deterministic(strategy):
    series = candles([100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96])

    first = strategy.generate(TOKEN, series)
    second = strategy.generate(TOKEN, series)

    assert first == second


def test_no_look_ahead_later_candles_cannot_change_an_earlier_signal(strategy):
    """The signal at bar N must not depend on bars after N."""
    prefix = candles([100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96])
    extended = candles([100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 200, 300, 50])

    on_prefix = strategy.generate(TOKEN, prefix)
    on_truncated_extension = strategy.generate(TOKEN, extended[: len(prefix)])

    assert on_prefix == on_truncated_extension


def test_minimum_candles_accounts_for_the_prior_bar(strategy):
    # slow_ema=6 needs 6 bars; a crossover needs the bar before that too.
    assert strategy.minimum_candles == 7


def test_minimum_candles_respects_a_long_rsi_period():
    strategy = MomentumStrategy(MomentumParams(fast_ema=3, slow_ema=6, rsi_period=20))

    assert strategy.minimum_candles == 22


def test_satisfies_the_strategy_protocol(strategy):
    assert isinstance(strategy, Strategy)


def test_fast_ema_must_be_shorter_than_slow():
    with pytest.raises(ValidationError, match="shorter than"):
        MomentumParams(fast_ema=26, slow_ema=12)


def test_equal_emas_are_rejected():
    with pytest.raises(ValidationError, match="shorter than"):
        MomentumParams(fast_ema=12, slow_ema=12)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rsi_oversold": Decimal("80"), "rsi_overbought": Decimal("70")},
        {"rsi_overbought": Decimal("120")},
        {"rsi_oversold": Decimal("0")},
    ],
)
def test_nonsensical_rsi_thresholds_are_rejected(kwargs):
    with pytest.raises(ValidationError, match="rsi"):
        MomentumParams(**kwargs)


def test_unknown_parameter_is_rejected():
    """A typo'd parameter must not be silently ignored."""
    with pytest.raises(ValidationError):
        MomentumParams(fast_emma=12)


@pytest.mark.parametrize("period", [0, -3])
def test_non_positive_periods_are_rejected(period):
    with pytest.raises(ValidationError):
        MomentumParams(rsi_period=period)


def test_registry_builds_the_configured_strategy():
    strategy = build_strategy(
        StrategyConfig(name="momentum", params={"fast_ema": 5, "slow_ema": 20})
    )

    assert strategy.name == "momentum"
    assert strategy.params.fast_ema == 5


def test_registry_rejects_an_unknown_strategy():
    """A typo must not silently fall back to a default."""
    with pytest.raises(ValueError, match="unknown strategy"):
        build_strategy(StrategyConfig(name="momentom"))


def test_registry_propagates_parameter_validation():
    with pytest.raises(ValidationError):
        build_strategy(StrategyConfig(name="momentum", params={"fast_ema": 99, "slow_ema": 2}))


def test_momentum_is_registered():
    assert "momentum" in available_strategies()


def test_shipped_config_params_are_valid():
    """The params in config.paper.yaml must actually build a strategy."""
    from pathlib import Path

    from core.config import load_config

    root = Path(__file__).resolve().parents[2]
    config = load_config(root / "config.paper.yaml", env={})

    assert build_strategy(config.strategy).name == "momentum"
