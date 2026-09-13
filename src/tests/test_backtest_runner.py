"""Backtest runner — the numbers it produces must be honest."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backtest.runner import BacktestResult, BacktestRunner, ClosedTrade
from core.config import BacktestConfig, CostsConfig, RiskConfig, RunConfig
from core.types import Candle, Mode
from strategy.strategy_momentum import MomentumParams, MomentumStrategy

TOKEN = "So11111111111111111111111111111111111111112"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def candles(prices, minutes: int = 15) -> list[Candle]:
    return [
        Candle(
            timestamp=START + timedelta(minutes=minutes * i),
            open=Decimal(str(p)),
            high=Decimal(str(p)),
            low=Decimal(str(p)),
            close=Decimal(str(p)),
            volume=Decimal("1000"),
        )
        for i, p in enumerate(prices)
    ]


@pytest.fixture
def config(tmp_path) -> RunConfig:
    return RunConfig(
        mode=Mode.BACKTEST,
        risk=RiskConfig(
            position_size_usd=Decimal("10"),
            max_slippage_pct=Decimal("0.5"),
            daily_loss_limit_usd=Decimal("20"),
            per_trade_stop_loss_pct=Decimal("5"),
            per_trade_take_profit_pct=Decimal("10"),
        ),
        costs=CostsConfig(sol_price_usd=Decimal("200")),
        backtest=BacktestConfig(
            initial_capital_usd=Decimal("100"),
            price_impact_pct=Decimal("0.0"),
            execution_slippage_pct=Decimal("0.3"),
        ),
        state_dir=tmp_path / "state",
        gate_file=tmp_path / "gate.json",
    )


@pytest.fixture
def strategy() -> MomentumStrategy:
    return MomentumStrategy(
        MomentumParams(fast_ema=3, slow_ema=6, rsi_period=5, rsi_overbought=Decimal("70"))
    )


def runner(config, strategy) -> BacktestRunner:
    return BacktestRunner(config, strategy)


# A dip that recovers into a crossover, then rallies hard enough to take
# profit, then falls away again.
TRENDING = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 102, 110, 120, 118, 105, 95, 90]


def test_empty_candles_produces_an_empty_result(config, strategy):
    result = runner(config, strategy).run(TOKEN, [])

    assert result.trade_count == 0
    assert result.candles_processed == 0
    assert result.net_pnl_usd == Decimal(0)
    assert result.max_drawdown_pct == Decimal(0)


def test_runs_end_to_end_and_produces_trades(config, strategy):
    result = runner(config, strategy).run(TOKEN, candles(TRENDING))

    assert result.signals_generated > 0
    assert result.trade_count >= 1


def test_net_pnl_is_gross_minus_fees(config, strategy):
    result = runner(config, strategy).run(TOKEN, candles(TRENDING))

    assert result.net_pnl_usd == result.gross_pnl_usd - result.total_fees_usd


def test_fees_are_always_charged(config, strategy):
    """A backtest with zero costs is the lie this project exists to avoid."""
    result = runner(config, strategy).run(TOKEN, candles(TRENDING))

    assert result.total_fees_usd > 0


def test_net_is_worse_than_gross_on_a_winning_run(config, strategy):
    result = runner(config, strategy).run(TOKEN, candles(TRENDING))

    assert result.net_pnl_usd < result.gross_pnl_usd


def test_is_deterministic_across_runs(config, strategy):
    series = candles(TRENDING)

    first = runner(config, strategy).run(TOKEN, series)
    second = runner(config, strategy).run(TOKEN, series)

    assert first.net_pnl_usd == second.net_pnl_usd
    assert first.trade_count == second.trade_count


def test_risk_state_does_not_leak_between_runs(config, strategy):
    """A halt in one backtest must not silently affect the next."""
    shared = runner(config, strategy)
    shared.risk.record_realized_pnl(Decimal("-50"), START)
    assert shared.risk.circuit_breaker.state(START).halted

    fresh = runner(config, strategy).run(TOKEN, candles(TRENDING))

    assert not fresh.block_reasons.get("circuit_breaker_tripped")


def test_entry_fills_are_worse_than_the_close(config, strategy):
    """Slippage is applied adversely, never favourably."""
    result = runner(config, strategy).run(TOKEN, candles(TRENDING))
    trade = result.trades[0]

    # Trades are stamped at the bar's close time, so the bar that produced
    # the entry is the one closing at `entry_at`.
    entry_candle = next(
        c
        for c in candles(TRENDING)
        if c.timestamp + timedelta(minutes=15) == trade.entry_at
    )
    assert trade.entry_price > entry_candle.close


def test_exit_fills_are_worse_than_the_close(config, strategy):
    result = runner(config, strategy).run(TOKEN, candles(TRENDING))
    trade = result.trades[0]

    # Same close-time semantics as the entry: match the bar that *ends* at
    # `exit_at`, not the one that opens on it.
    exit_candle = next(
        c
        for c in candles(TRENDING)
        if c.timestamp + timedelta(minutes=15) == trade.exit_at
    )
    assert trade.exit_price < exit_candle.close


def test_no_trades_when_risk_blocks_every_entry(config, strategy):
    """Tighten the slippage cap below assumed slippage and nothing opens."""
    tightened = config.model_copy(
        update={"risk": config.risk.model_copy(update={"max_slippage_pct": Decimal("0.1")})}
    )

    result = runner(tightened, strategy).run(TOKEN, candles(TRENDING))

    assert result.trade_count == 0
    assert result.entries_blocked_by_risk > 0
    assert result.block_reasons["slippage_exceeded"] > 0


def test_circuit_breaker_stops_further_entries(config, strategy):
    """Losses inside one UTC day must eventually halt the backtest's trading."""
    tight = config.model_copy(
        update={
            "risk": config.risk.model_copy(
                update={"daily_loss_limit_usd": Decimal("0.5")}
            )
        }
    )
    # A long sawtooth inside a single day: repeated small losing round trips.
    prices: list[float] = []
    for _ in range(8):
        prices += [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 92, 88, 84]

    result = runner(tight, strategy).run(TOKEN, candles(prices, minutes=1))

    assert result.block_reasons.get("circuit_breaker_tripped", 0) > 0


def test_stop_loss_closes_a_position(config, strategy):
    prices = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 80, 70, 60]

    result = runner(config, strategy).run(TOKEN, candles(prices))

    assert any(t.exit_reason == "stop_loss" for t in result.trades)


def test_take_profit_closes_a_position(config):
    """Needs the RSI exit disabled — otherwise it fires first on this series.

    That ordering is itself correct: on a sharp rally RSI goes overbought
    well before a 10% take-profit is reached, so the strategy's own exit
    wins. Here we isolate the take-profit path.
    """
    patient = MomentumStrategy(
        MomentumParams(fast_ema=3, slow_ema=6, rsi_period=5, rsi_overbought=Decimal("99"))
    )
    quick_profit = config.model_copy(
        update={
            "risk": config.risk.model_copy(
                update={"per_trade_take_profit_pct": Decimal("3")}
            )
        }
    )

    result = runner(quick_profit, patient).run(TOKEN, candles(TRENDING))

    assert any(t.exit_reason == "take_profit" for t in result.trades)


def test_stops_are_checked_before_the_strategy_signal(config):
    """A stop-loss must win over a strategy HOLD, not wait for a SELL."""
    patient = MomentumStrategy(
        MomentumParams(fast_ema=3, slow_ema=6, rsi_period=5, rsi_overbought=Decimal("99"))
    )
    prices = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 94, 92, 90]

    result = runner(config, patient).run(TOKEN, candles(prices))

    assert any(t.exit_reason == "stop_loss" for t in result.trades)


def test_equity_curve_tracks_capital(config, strategy):
    result = runner(config, strategy).run(TOKEN, candles(TRENDING))

    assert result.equity_curve[0] == Decimal("100")
    assert result.equity_curve[-1] == result.final_equity_usd


def test_no_look_ahead_a_prefix_run_matches_the_truncated_full_run(config, strategy):
    """Later candles must not change what happened earlier."""
    full = candles(TRENDING)
    prefix = full[:12]

    on_prefix = runner(config, strategy).run(TOKEN, prefix)
    on_full = runner(config, strategy).run(TOKEN, full)

    # Every trade that closed within the prefix window must be identical.
    # The window ends when its last bar closes, not when that bar opens.
    prefix_ends = prefix[-1].timestamp + timedelta(minutes=15)
    closed_in_window = [t for t in on_full.trades if t.exit_at <= prefix_ends]
    assert on_prefix.trades == closed_in_window


def test_reports_an_open_position_at_the_end(config, strategy):
    prices = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 97]

    result = runner(config, strategy).run(TOKEN, candles(prices))

    assert result.open_position_at_end is True


def test_win_rate_counts_net_wins_not_gross(config):
    """A trade that gains gross but loses to fees is not a win."""
    trade = ClosedTrade(
        token_mint=TOKEN,
        entry_at=START,
        exit_at=START + timedelta(minutes=15),
        entry_price=Decimal("100"),
        exit_price=Decimal("100.05"),
        size_usd=Decimal("10"),
        fees_usd=Decimal("0.42"),
        exit_reason="take_profit",
    )

    assert trade.gross_pnl_usd > 0
    assert trade.net_pnl_usd < 0
    assert trade.is_win is False


def test_max_drawdown_measures_peak_to_trough():
    result = BacktestResult(
        token_mint=TOKEN,
        strategy_name="momentum",
        candles_processed=0,
        first_candle_at=None,
        last_candle_at=None,
        initial_capital_usd=Decimal("100"),
        equity_curve=[Decimal(100), Decimal(120), Decimal(90), Decimal(110)],
    )

    # Peak 120 down to 90 is a 25% drawdown.
    assert result.max_drawdown_pct == Decimal("25")


def test_expectancy_is_zero_with_no_trades():
    result = BacktestResult(
        token_mint=TOKEN,
        strategy_name="momentum",
        candles_processed=0,
        first_candle_at=None,
        last_candle_at=None,
        initial_capital_usd=Decimal("100"),
    )

    assert result.expectancy_usd == Decimal(0)
    assert result.win_rate_pct == Decimal(0)


def wicked(bars, minutes: int = 15) -> list[Candle]:
    """Candles carrying a real intrabar range: (close, low) per bar."""
    return [
        Candle(
            timestamp=START + timedelta(minutes=minutes * i),
            open=Decimal(str(close)),
            high=Decimal(str(close)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=Decimal("1000"),
        )
        for i, (close, low) in enumerate(bars)
    ]


def test_a_stop_hit_intrabar_fires_even_when_the_close_recovers(config, strategy):
    """The bug: scoring only the close skips stops the position really took.

    The final bar closes down ~1% (no stop on close) but its low dips 12%
    below the entry, well past the 5% stop. That stop was hit in real life,
    so it must fire here.
    """
    flat = [(p, p) for p in [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96]]
    series = wicked(flat + [(95, 85)])

    result = runner(config, strategy).run(TOKEN, series)

    assert result.trades, "expected the series to open a position"
    stopped = [t for t in result.trades if t.exit_reason == "stop_loss"]
    assert stopped, "intrabar stop was missed — close-only evaluation regressed"
    # Exit is marked at the stop level (adversely), not at the bar's close.
    assert stopped[-1].exit_price < Decimal("95")


def test_close_only_dip_does_not_invent_a_stop(config, strategy):
    """The mirror case: no wick, no stop. Guards against over-triggering."""
    flat = [(p, p) for p in [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 95]]

    result = runner(config, strategy).run(TOKEN, wicked(flat))

    assert not [t for t in result.trades if t.exit_reason == "stop_loss"]


def test_trades_are_stamped_at_the_bar_close_not_the_bar_open(config, strategy):
    """A bar's close is unknowable until the bar ends.

    Stamping a decision at the bar's open backdates every trade by one
    full interval and buckets the daily circuit breaker on the wrong day.
    """
    series = candles(TRENDING)
    close_times = {c.timestamp + timedelta(minutes=15) for c in series}
    open_times = {c.timestamp for c in series}

    result = runner(config, strategy).run(TOKEN, series)

    assert result.trades
    for trade in result.trades:
        assert trade.entry_at in close_times
        assert trade.exit_at in close_times
        # The first bar's open is the one time that is not also a close.
        assert trade.entry_at != min(open_times)
