"""Backtest report — net-of-fees numbers must be impossible to miss."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backtest.report import render_report, report_filename, write_report
from backtest.runner import BacktestResult, ClosedTrade

TOKEN = "So11111111111111111111111111111111111111112"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)
PARAMS = {"fast_ema": 12, "slow_ema": 26, "rsi_period": 14}


def trade(gross_up: str = "5", fees: str = "0.42") -> ClosedTrade:
    return ClosedTrade(
        token_mint=TOKEN,
        entry_at=START,
        exit_at=START + timedelta(minutes=45),
        entry_price=Decimal("100"),
        exit_price=Decimal("100") * (Decimal(1) + Decimal(gross_up) / Decimal(100)),
        size_usd=Decimal("10"),
        fees_usd=Decimal(fees),
        exit_reason="take_profit",
    )


def result(trades=None, **overrides) -> BacktestResult:
    base = BacktestResult(
        token_mint=TOKEN,
        strategy_name="momentum",
        candles_processed=200,
        first_candle_at=START,
        last_candle_at=START + timedelta(days=5),
        initial_capital_usd=Decimal("100"),
        trades=list(trades or []),
        equity_curve=[Decimal("100"), Decimal("110"), Decimal("95")],
        signals_generated=180,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def render(res=None) -> str:
    return render_report(res or result([trade()]), PARAMS, "GeckoTerminal", "15m")


def test_leads_with_net_pnl():
    report = render()

    assert "Net P&L" in report
    assert "**Net P&L (after fees & slippage)**" in report


def test_shows_gross_and_fees_alongside_net():
    report = render()

    assert "Gross P&L" in report
    assert "Total fees & costs" in report
    assert "Cost drag" in report


def test_records_provenance_for_reproducibility():
    report = render()

    assert "GeckoTerminal" in report
    assert "15m" in report
    assert "fast_ema" in report
    assert START.isoformat() in report


def test_flags_a_failing_expectancy_explicitly():
    """A losing run must say so, not leave it to be worked out."""
    report = render(result([trade(gross_up="0.1", fees="0.42")]))

    assert "does not clear the validation gate" in report


def test_positive_expectancy_still_says_the_gate_needs_more():
    report = render(result([trade(gross_up="20", fees="0.42")]))

    assert "not sufficient" in report
    assert "30 days of paper trading" in report


def test_lists_trades():
    report = render(result([trade(), trade()]))

    assert report.count("| `take_profit` |") == 2


def test_reports_block_reasons_when_present():
    report = render(
        result([trade()], entries_blocked_by_risk=3, block_reasons={"slippage_exceeded": 3})
    )

    assert "Why entries were blocked" in report
    assert "`slippage_exceeded`" in report


def test_omits_block_table_when_nothing_was_blocked():
    assert "Why entries were blocked" not in render()


def test_always_states_the_slippage_caveat():
    """The assumption must travel with the number it flatters."""
    report = render()

    assert "**measured** price-impact" in report
    assert "**assumed**" in report
    assert "do not tune parameters on the same data" in report


def test_handles_a_run_with_no_trades():
    report = render(result([]))

    assert "0 trades" in report
    assert "does not clear the validation gate" in report


def test_handles_a_run_with_no_candles():
    empty = BacktestResult(
        token_mint=TOKEN,
        strategy_name="momentum",
        candles_processed=0,
        first_candle_at=None,
        last_candle_at=None,
        initial_capital_usd=Decimal("100"),
    )

    assert "no candles" in render_report(empty, PARAMS, "GeckoTerminal", "15m")


def test_includes_optional_notes():
    report = render_report(
        result([trade()]), PARAMS, "GeckoTerminal", "15m", notes="Chosen for the Sept selloff."
    )

    assert "Chosen for the Sept selloff." in report


def test_filename_follows_the_research_convention():
    name = report_filename(result([trade()]), "SOL USDC 15m", run_date=date(2026, 9, 9))

    assert name == "2026-09-09_momentum_sol-usdc-15m.md"


def test_filename_sanitises_a_hostile_summary():
    name = report_filename(result(), "../../etc/passwd", run_date=date(2026, 9, 9))

    assert "/" not in name
    assert ".." not in name


def test_write_report_creates_the_file(tmp_path):
    path = write_report(
        result([trade()]),
        PARAMS,
        "GeckoTerminal",
        "15m",
        output_dir=tmp_path / "backtests",
        summary="sol-usdc",
        run_date=date(2026, 9, 9),
    )

    assert path.is_file()
    assert "Net P&L" in path.read_text()


@pytest.mark.parametrize("gross_up,fees", [("5", "0.42"), ("0.1", "0.42"), ("-3", "0.42")])
def test_net_always_equals_gross_minus_fees_in_the_report(gross_up, fees):
    res = result([trade(gross_up=gross_up, fees=fees)])

    assert res.net_pnl_usd == res.gross_pnl_usd - res.total_fees_usd
