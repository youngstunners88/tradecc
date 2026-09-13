"""Re-run the Stage 5 backtests with each cost correction isolated.

Four corrections landed at once and two of them pull in opposite
directions, so a single before/after number would hide which did the
work. This applies them cumulatively and prints the marginal effect of
each.

    PYTHONPATH=src python research/cost_model_delta.py

Analysis tool, not part of the bot.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backtest.runner import BacktestRunner  # noqa: E402
from core.config import BacktestConfig, CostsConfig, load_config  # noqa: E402
from execution.candle_cache import CandleCache  # noqa: E402
from strategy.strategy_momentum import MomentumParams, MomentumStrategy  # noqa: E402

INTERVALS = ["1h", "15m"]

# Each stage adds one correction to the one before it, so the marginal
# effect of a single change is the difference between adjacent rows.
#
# `compute_unit_limit=1` reproduces the original bug exactly: it makes the
# microlamport figure behave as a flat total (200_000 uL = 0.2 lamports)
# rather than a price per compute unit.
STAGES = [
    (
        "0. as recorded (flat priority, no Jito, 0.3%/side)",
        dict(compute_unit_limit=1, jito_tip_lamports=0),
        dict(price_impact_pct=Decimal("0"), execution_slippage_pct=Decimal("0.3")),
    ),
    (
        "1. + priority fee per compute unit",
        dict(compute_unit_limit=200_000, jito_tip_lamports=0),
        dict(price_impact_pct=Decimal("0"), execution_slippage_pct=Decimal("0.3")),
    ),
    (
        "2. + Jito tip modelled",
        dict(compute_unit_limit=200_000, jito_tip_lamports=17_392),
        dict(price_impact_pct=Decimal("0"), execution_slippage_pct=Decimal("0.3")),
    ),
    (
        "3. + measured price impact (0.3% -> 0.11%/side)",
        dict(compute_unit_limit=200_000, jito_tip_lamports=17_392),
        dict(price_impact_pct=Decimal("0.01"), execution_slippage_pct=Decimal("0.10")),
    ),
]


def run(config, candles, costs_over, backtest_over):
    updated = config.model_copy(
        update={
            "costs": CostsConfig(**{**config.costs.model_dump(), **costs_over}),
            "backtest": BacktestConfig(
                **{**config.backtest.model_dump(), **backtest_over}
            ),
        }
    )
    strategy = MomentumStrategy(MomentumParams())
    return BacktestRunner(updated, strategy).run(
        config.strategy.token_mints[0], candles
    )


def main() -> int:
    config = load_config("config.backtest.yaml", env={})
    cache = CandleCache(config.data.cache_dir)

    print("Every row below prices SOL-denominated costs from each bar's own")
    print("close, replacing the static $200 constant the recorded run used.\n")

    for interval in INTERVALS:
        candles = cache.load(config.paper.pool_address, interval)
        mean_sol = sum(c.close for c in candles) / Decimal(len(candles))
        print(f"{'=' * 78}")
        print(
            f"{interval}  |  {len(candles)} candles  "
            f"{candles[0].timestamp.date()} -> {candles[-1].timestamp.date()}  |  "
            f"mean SOL ${mean_sol:.2f} (config constant said $200)"
        )
        print(f"{'=' * 78}")
        print(
            f"{'stage':<52}{'trades':>7}{'gross':>9}{'fees':>8}{'net':>9}{'delta':>9}"
        )

        previous_net = None
        for label, costs_over, backtest_over in STAGES:
            result = run(config, candles, costs_over, backtest_over)
            net = result.net_pnl_usd
            delta = "" if previous_net is None else f"{net - previous_net:+8.4f}"
            print(
                f"{label:<52}{result.trade_count:>7}"
                f"{result.gross_pnl_usd:>9.4f}{result.total_fees_usd:>8.4f}"
                f"{net:>9.4f}{delta:>9}"
            )
            previous_net = net
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
