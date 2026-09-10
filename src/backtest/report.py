"""Backtest report in the `research/backtests/` format.

Per `research/CONTEXT.md`, net-of-fees numbers are the ones that matter —
gross P&L is misleading at $5–$10 sizes, where fixed costs can exceed the
edge. So the report leads with net, shows gross beside it, and states the
cost drag explicitly rather than leaving it to be inferred.

It also records the parameters, date range, and data source, so a result
can be reproduced or challenged later instead of being taken on trust.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtest.runner import BacktestResult

MONEY = Decimal("0.0001")
PERCENT = Decimal("0.01")


def _money(value: Decimal) -> str:
    return f"{value.quantize(MONEY):,}"


def _pct(value: Decimal) -> str:
    return f"{value.quantize(PERCENT)}%"


def report_filename(result: BacktestResult, summary: str, run_date: date | None = None) -> str:
    """`YYYY-MM-DD_<strategy>_<summary>.md`, per research/CONTEXT.md."""
    stamp = (run_date or date.today()).isoformat()
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in summary).strip("-").lower()
    return f"{stamp}_{result.strategy_name}_{slug}.md"


def render_report(
    result: BacktestResult,
    params: dict[str, Any],
    data_source: str,
    interval: str,
    notes: str = "",
) -> str:
    date_range = "no candles"
    if result.first_candle_at and result.last_candle_at:
        date_range = (
            f"{result.first_candle_at.isoformat()} → {result.last_candle_at.isoformat()}"
        )

    cost_drag = (
        result.total_fees_usd / abs(result.gross_pnl_usd) * Decimal(100)
        if result.gross_pnl_usd
        else Decimal(0)
    )

    lines = [
        f"# Backtest — {result.strategy_name} on {result.token_mint}",
        "",
        "## Verdict",
        "",
        f"**Net P&L: {_money(result.net_pnl_usd)} USD** over {result.trade_count} trades "
        f"(expectancy {_money(result.expectancy_usd)} USD/trade).",
        "",
        (
            "> Net expectancy is not positive. This strategy/parameter set does "
            "not clear the validation gate."
            if result.expectancy_usd <= 0
            else "> Net expectancy is positive. Necessary for the validation gate, "
            "not sufficient — the gate also requires 30 days of paper trading "
            "and a max drawdown inside a threshold set beforehand."
        ),
        "",
        "## Run parameters",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Strategy | `{result.strategy_name}` |",
        f"| Token | `{result.token_mint}` |",
        f"| Data source | {data_source} |",
        f"| Candle interval | {interval} |",
        f"| Date range | {date_range} |",
        f"| Candles | {result.candles_processed} |",
        f"| Initial capital | {_money(result.initial_capital_usd)} USD |",
    ]
    for key in sorted(params):
        lines.append(f"| `{key}` | {params[key]} |")

    lines += [
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Net P&L (after fees & slippage)** | **{_money(result.net_pnl_usd)} USD** |",
        f"| Gross P&L | {_money(result.gross_pnl_usd)} USD |",
        f"| Total fees & costs | {_money(result.total_fees_usd)} USD |",
        f"| Cost drag (fees ÷ \\|gross\\|) | {_pct(cost_drag)} |",
        f"| Expectancy per trade (net) | {_money(result.expectancy_usd)} USD |",
        f"| Trades | {result.trade_count} |",
        f"| Win rate (net of costs) | {_pct(result.win_rate_pct)} |",
        f"| Max drawdown | {_pct(result.max_drawdown_pct)} |",
        f"| Final equity | {_money(result.final_equity_usd)} USD |",
        "",
        "## Execution detail",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Signals evaluated | {result.signals_generated} |",
        f"| Entries blocked by risk | {result.entries_blocked_by_risk} |",
        f"| Position open at end | {'yes' if result.open_position_at_end else 'no'} |",
    ]

    if result.block_reasons:
        lines += ["", "### Why entries were blocked", "", "| Reason | Count |", "|---|---|"]
        for reason in sorted(result.block_reasons):
            lines.append(f"| `{reason}` | {result.block_reasons[reason]} |")

    if result.trades:
        lines += [
            "",
            "## Trades",
            "",
            "| # | Entry | Exit | Entry px | Exit px | Gross | Fees | Net | Reason |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for i, trade in enumerate(result.trades, start=1):
            lines.append(
                f"| {i} | {trade.entry_at.isoformat()} | {trade.exit_at.isoformat()} "
                f"| {trade.entry_price.quantize(MONEY)} | {trade.exit_price.quantize(MONEY)} "
                f"| {_money(trade.gross_pnl_usd)} | {_money(trade.fees_usd)} "
                f"| {_money(trade.net_pnl_usd)} | `{trade.exit_reason}` |"
            )

    lines += [
        "",
        "## Caveats",
        "",
        "- Adverse price movement is applied as a constant, because historical "
        "candles carry no quotes. It splits into a **measured** price-impact "
        "component (calibrated from Jupiter's `priceImpactPct` at real size — "
        "see `research/calibrate_costs.py`) and an **assumed** "
        "execution-slippage component. See `BacktestConfig`.",
        "- Fills are modelled at the adverse side of that total on both entry "
        "and exit.",
        "- A single backtest over one date range is weak evidence. Note why "
        "this range was chosen, and do not tune parameters on the same data "
        "used to evaluate them.",
    ]
    if notes:
        lines += ["", "## Notes", "", notes]

    return "\n".join(lines) + "\n"


def write_report(
    result: BacktestResult,
    params: dict[str, Any],
    data_source: str,
    interval: str,
    output_dir: Path | str,
    summary: str,
    notes: str = "",
    run_date: date | None = None,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / report_filename(result, summary, run_date)
    path.write_text(render_report(result, params, data_source, interval, notes))
    return path
