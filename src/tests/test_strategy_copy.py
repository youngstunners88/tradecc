"""The copy strategy: the look-ahead boundary, and purity.

`Strategy.generate` is contractually a pure function of closed candles. Copying
needs source-wallet fills, and the obvious implementation fetches them inside
`generate()` — which destroys replayability and makes the backtest measure
something other than what runs. The fill log is therefore frozen and injected
at construction, and eligibility is decided by comparing
`fill.timestamp + lag` against `candles[-1].timestamp`.

That comparison is both the lag model and the look-ahead boundary, so it is
what these tests attack hardest. Every boundary case is asserted on the exact
second, and `test_the_boundary_is_not_off_by_one_second` fails if the
comparison is loosened by a single second in either direction.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.config import StrategyConfig
from core.types import Candle, SignalType
from strategy.registry import build_strategy
from strategy.strategy_copy import NAME, CopyStrategy, SourceFill

MINT = "So11111111111111111111111111111111111111112"
OTHER_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WALLET = "wallet_one"
T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
LAG = 60


def fill(at: datetime, side: str = "buy", wallet: str = WALLET, mint: str = MINT) -> SourceFill:
    return SourceFill(
        timestamp=at, wallet=wallet, token_mint=mint, side=side, amount=Decimal("10")
    )


def candle(at: datetime, close: str = "100") -> Candle:
    price = Decimal(close)
    return Candle(
        timestamp=at, open=price, high=price, low=price, close=price, volume=Decimal("1")
    )


def signal_at(strategy: CopyStrategy, at: datetime, mint: str = MINT):
    return strategy.generate(mint, [candle(at)])


# --- the look-ahead boundary -----------------------------------------------


def test_a_fill_is_not_visible_before_the_lag_has_elapsed() -> None:
    strategy = CopyStrategy(fills=[fill(T0)], lag_seconds=LAG)
    assert signal_at(strategy, T0).type is SignalType.HOLD
    assert signal_at(strategy, T0 + timedelta(seconds=LAG - 1)).type is SignalType.HOLD


def test_a_fill_becomes_visible_exactly_at_the_lag() -> None:
    strategy = CopyStrategy(fills=[fill(T0)], lag_seconds=LAG)
    assert signal_at(strategy, T0 + timedelta(seconds=LAG)).type is SignalType.BUY


def test_the_boundary_is_not_off_by_one_second() -> None:
    """The whole lag model is one comparison. This pins it on both sides.

    A `<` where the code has `<=` fails the second assertion; a `<=` applied
    to `fill.timestamp` instead of `fill.timestamp + lag` fails the first.
    """
    strategy = CopyStrategy(fills=[fill(T0)], lag_seconds=LAG)
    boundary = T0 + timedelta(seconds=LAG)

    assert signal_at(strategy, boundary - timedelta(seconds=1)).type is SignalType.HOLD
    assert signal_at(strategy, boundary).type is SignalType.BUY


def test_a_future_fill_is_never_consulted() -> None:
    """A fill after the current candle must not influence the signal at all —
    not even by being the most recent one on the books."""
    fills = [fill(T0, side="buy"), fill(T0 + timedelta(hours=1), side="sell")]
    strategy = CopyStrategy(fills=fills, lag_seconds=LAG)

    # The later SELL is in the future here; only the earlier BUY is eligible.
    assert signal_at(strategy, T0 + timedelta(seconds=LAG)).type is SignalType.BUY


def test_the_most_recent_eligible_fill_wins() -> None:
    fills = [
        fill(T0, side="buy"),
        fill(T0 + timedelta(minutes=5), side="sell"),
    ]
    strategy = CopyStrategy(fills=fills, lag_seconds=LAG)
    at = T0 + timedelta(minutes=5, seconds=LAG)
    assert signal_at(strategy, at).type is SignalType.SELL


def test_a_longer_lag_delays_visibility_proportionally() -> None:
    strategy = CopyStrategy(fills=[fill(T0)], lag_seconds=300)
    assert signal_at(strategy, T0 + timedelta(seconds=299)).type is SignalType.HOLD
    assert signal_at(strategy, T0 + timedelta(seconds=300)).type is SignalType.BUY


# --- purity ----------------------------------------------------------------


def test_the_same_inputs_produce_the_same_signal() -> None:
    strategy = CopyStrategy(fills=[fill(T0)], lag_seconds=LAG)
    at = T0 + timedelta(seconds=LAG)
    first, second = signal_at(strategy, at), signal_at(strategy, at)
    assert (first.type, first.price, first.timestamp, first.metadata) == (
        second.type,
        second.price,
        second.timestamp,
        second.metadata,
    )


def test_mutating_the_caller_s_fill_list_does_not_change_the_strategy() -> None:
    """The log is frozen at construction so a run cannot change what it is
    replaying halfway through."""
    fills = [fill(T0)]
    strategy = CopyStrategy(fills=fills, lag_seconds=LAG)
    fills.append(fill(T0 + timedelta(minutes=1), side="sell"))

    at = T0 + timedelta(minutes=1, seconds=LAG)
    assert signal_at(strategy, at).type is SignalType.BUY


def test_fills_are_sorted_regardless_of_input_order() -> None:
    fills = [fill(T0 + timedelta(minutes=5), side="sell"), fill(T0, side="buy")]
    strategy = CopyStrategy(fills=fills, lag_seconds=LAG)
    assert signal_at(strategy, T0 + timedelta(seconds=LAG)).type is SignalType.BUY


# --- scoping ---------------------------------------------------------------


def test_a_fill_on_another_token_does_not_produce_a_signal() -> None:
    strategy = CopyStrategy(fills=[fill(T0, mint=OTHER_MINT)], lag_seconds=LAG)
    assert signal_at(strategy, T0 + timedelta(seconds=LAG)).type is SignalType.HOLD


def test_the_allowlist_filters_at_construction() -> None:
    fills = [fill(T0, wallet="not_allowed"), fill(T0, wallet=WALLET)]
    strategy = CopyStrategy(fills=fills, lag_seconds=LAG, allowlist=[WALLET])
    at = T0 + timedelta(seconds=LAG)
    assert signal_at(strategy, at).metadata["source_wallet"] == WALLET


def test_a_wallet_off_the_allowlist_is_silent() -> None:
    strategy = CopyStrategy(
        fills=[fill(T0, wallet="not_allowed")], lag_seconds=LAG, allowlist=[WALLET]
    )
    assert signal_at(strategy, T0 + timedelta(seconds=LAG)).type is SignalType.HOLD


# --- signal shape ----------------------------------------------------------


def test_the_signal_is_traceable_to_the_fill_that_caused_it() -> None:
    strategy = CopyStrategy(fills=[fill(T0)], lag_seconds=LAG)
    result = signal_at(strategy, T0 + timedelta(seconds=LAG))

    assert result.metadata["source_wallet"] == WALLET
    assert result.metadata["source_fill_ts"] == T0.isoformat()
    assert all(isinstance(v, str) for v in result.metadata.values())
    assert result.strategy == NAME
    assert not hasattr(result, "size"), "sizing belongs to risk/, not to a strategy"


def test_price_and_timestamp_come_from_the_latest_candle() -> None:
    strategy = CopyStrategy(fills=[fill(T0)], lag_seconds=LAG)
    at = T0 + timedelta(seconds=LAG)
    result = strategy.generate(MINT, [candle(T0), candle(at, close="123.45")])
    assert result.price == Decimal("123.45")
    assert result.timestamp == at


# --- construction and config ----------------------------------------------


def test_sub_minute_lag_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 60"):
        CopyStrategy(fills=[], lag_seconds=59)


def test_a_naive_timestamp_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceFill(
            timestamp=datetime(2026, 6, 1, 12, 0),
            wallet=WALLET,
            token_mint=MINT,
            side="buy",
            amount=Decimal("10"),
        )


def test_an_unrecognised_side_is_refused() -> None:
    with pytest.raises(ValueError, match="buy.*sell"):
        SourceFill(
            timestamp=T0, wallet=WALLET, token_mint=MINT, side="long", amount=Decimal("1")
        )


def test_the_registry_builds_it_by_name() -> None:
    strategy = build_strategy(StrategyConfig(name="copy", params={"allowlist": [WALLET]}))
    assert isinstance(strategy, CopyStrategy)
    assert strategy.name == NAME


def test_a_typo_in_the_strategy_name_raises() -> None:
    with pytest.raises(ValueError, match="unknown strategy"):
        build_strategy(StrategyConfig(name="coppy"))


def test_an_unknown_param_is_rejected_not_ignored() -> None:
    with pytest.raises(ValueError, match="lag_secondz"):
        build_strategy(StrategyConfig(name="copy", params={"lag_secondz": 60}))


def test_a_config_built_strategy_refuses_to_run_without_fills() -> None:
    """The silent-no-op trap: YAML cannot carry a fill log, so a config-built
    strategy would otherwise HOLD forever — indistinguishable from a working
    strategy in a quiet market, and good for burning an entire test window."""
    strategy = build_strategy(StrategyConfig(name="copy", params={"allowlist": [WALLET]}))
    with pytest.raises(ValueError, match="no fill log"):
        signal_at(strategy, T0)


def test_with_fills_produces_a_runnable_strategy_and_keeps_the_allowlist() -> None:
    configured = build_strategy(StrategyConfig(name="copy", params={"allowlist": [WALLET]}))
    runnable = configured.with_fills([fill(T0), fill(T0, wallet="not_allowed")])

    result = signal_at(runnable, T0 + timedelta(seconds=LAG))
    assert result.type is SignalType.BUY
    assert result.metadata["source_wallet"] == WALLET
    # The original is untouched — with_fills returns a new instance.
    with pytest.raises(ValueError, match="no fill log"):
        signal_at(configured, T0)
