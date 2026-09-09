"""Parameter sweep over the tuning range only.

Protocol is fixed in planning/decisions/2026-09-09-tuning-holdout-split.md
and this script implements it literally:

- The held-out slice is never scored here. `--phase tune` cannot load it.
- Selection is by net expectancy with a minimum trade count, decided
  before the sweep ran.
- `--phase holdout` evaluates exactly one configuration per interval.

Kept in research/ rather than src/ because it is an analysis tool, not
part of the bot.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backtest.runner import BacktestRunner  # noqa: E402
from core.config import load_config  # noqa: E402
from core.types import Candle  # noqa: E402
from execution.candle_cache import CandleCache  # noqa: E402
from strategy.strategy_momentum import MomentumParams, MomentumStrategy  # noqa: E402

# --- fixed in the decision record, before any parameter was tried ---
SPLIT_FRACTION = Decimal("0.70")
MIN_TRADES = 10
GRID = {
    "fast_ema": [5, 8, 12, 20],
    "slow_ema": [21, 26, 34, 50],
    "rsi_period": [7, 14, 21],
    "rsi_overbought": [Decimal("60"), Decimal("70"), Decimal("80")],
}
INTERVALS = ["1h", "4h", "1d"]


def split_candles(candles: list[Candle]) -> tuple[list[Candle], list[Candle]]:
    boundary = int(len(candles) * float(SPLIT_FRACTION))
    return candles[:boundary], candles[boundary:]


def combinations():
    keys = list(GRID)
    for values in itertools.product(*(GRID[k] for k in keys)):
        params = dict(zip(keys, values))
        if params["fast_ema"] >= params["slow_ema"]:
            continue
        yield params


def score(config, candles: list[Candle], params: dict, token: str) -> dict:
    strategy = MomentumStrategy(MomentumParams(**params))
    if len(candles) < strategy.minimum_candles + 5:
        return {"trades": 0, "net": Decimal(0), "expectancy": Decimal(0)}
    result = BacktestRunner(config, strategy).run(token, candles)
    return {
        "trades": result.trade_count,
        "net": result.net_pnl_usd,
        "gross": result.gross_pnl_usd,
        "fees": result.total_fees_usd,
        "expectancy": result.expectancy_usd,
        "win_rate": result.win_rate_pct,
        "max_dd": result.max_drawdown_pct,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["tune", "holdout"], required=True)
    parser.add_argument("--config", default="config.backtest.yaml")
    parser.add_argument("--winners", default="research/.sweep-winners.json")
    args = parser.parse_args()

    config = load_config(args.config, env={})
    token = config.strategy.token_mints[0]
    cache = CandleCache(config.data.cache_dir)

    if args.phase == "tune":
        winners = {}
        for interval in INTERVALS:
            candles = cache.load(config.paper.pool_address, interval)
            tuning, _holdout = split_candles(candles)
            # _holdout is deliberately discarded, unscored.
            print(f"\n=== {interval}: tuning on {len(tuning)} candles "
                  f"({tuning[0].timestamp.date()} -> {tuning[-1].timestamp.date()}) ===")

            scored = []
            for params in combinations():
                stats = score(config, tuning, params, token)
                scored.append((params, stats))

            eligible = [(p, s) for p, s in scored if s["trades"] >= MIN_TRADES]
            print(f"{len(scored)} combinations, {len(eligible)} with >= {MIN_TRADES} trades")
            if not eligible:
                print(f"  NO ELIGIBLE CONFIGURATION at {interval} (too few trades)")
                continue

            eligible.sort(key=lambda item: item[1]["expectancy"], reverse=True)
            best_params, best = eligible[0]
            winners[interval] = {k: str(v) for k, v in best_params.items()}
            print(f"  winner: {best_params}")
            print(f"    trades={best['trades']} net={best['net']:.4f} "
                  f"expectancy={best['expectancy']:.4f} win={best['win_rate']:.1f}% "
                  f"maxDD={best['max_dd']:.2f}%")
            positive = sum(1 for _, s in eligible if s["expectancy"] > 0)
            print(f"    {positive}/{len(eligible)} eligible configs had positive net expectancy")

        Path(args.winners).write_text(json.dumps(winners, indent=2))
        print(f"\nwinners written to {args.winners}")
        return 0

    # --- holdout: one configuration per interval, no re-picking ---
    winners = json.loads(Path(args.winners).read_text())
    print("HELD-OUT EVALUATION — one configuration per interval, as fixed in advance\n")
    for interval, raw in winners.items():
        params = {
            "fast_ema": int(raw["fast_ema"]),
            "slow_ema": int(raw["slow_ema"]),
            "rsi_period": int(raw["rsi_period"]),
            "rsi_overbought": Decimal(raw["rsi_overbought"]),
        }
        candles = cache.load(config.paper.pool_address, interval)
        tuning, holdout = split_candles(candles)
        tuned = score(config, tuning, params, token)
        held = score(config, holdout, params, token)
        print(f"=== {interval} · {params} ===")
        print(f"  tuning  ({tuning[0].timestamp.date()}->{tuning[-1].timestamp.date()}): "
              f"trades={tuned['trades']:>3} net={tuned['net']:>9.4f} "
              f"expectancy={tuned['expectancy']:>8.4f}")
        print(f"  HELDOUT ({holdout[0].timestamp.date()}->{holdout[-1].timestamp.date()}): "
              f"trades={held['trades']:>3} net={held['net']:>9.4f} "
              f"expectancy={held['expectancy']:>8.4f} "
              f"win={held.get('win_rate', 0):.1f}% maxDD={held.get('max_dd', 0):.2f}%")
        if held["trades"]:
            print(f"           gross={held['gross']:.4f} fees={held['fees']:.4f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
