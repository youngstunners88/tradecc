"""Re-run every recorded negative at $5 / $10 / $25 / $100.

The question is not "would bigger positions make more money" — a positive
return scales trivially. It is whether any recorded negative **flips, and
whether the flip tracks the fee curve**:

    $5 -> 0.47%   $10 -> 0.35%   $25 -> 0.27%   $100 -> 0.23%   per round trip

The interpretation rule is fixed in
`planning/decisions/2026-09-13-capital-range-sensitivity.md` and was committed
before this file existed. Rule 2 in particular: a verdict still negative at
$100 means the signal has no edge, not that it needs more capital.

## Scaling, and why

Position size is scaled. Two other settings are scaled **with** it, because
they are denominated in absolute dollars and holding them fixed would make the
large-size runs a test of the circuit breaker rather than of fee drag:

- `daily_loss_limit_usd` — kept at 2x position size, the default $10/$20 ratio.
  Held at $20 while size went to $100, a single stop-loss would breach the
  daily limit and halt the day, truncating results for a reason unrelated to
  costs. (`RiskConfig` refuses that configuration outright, which is the
  validator doing its job.)
- `initial_capital_usd` — kept at 10x position size, the default $10/$100
  ratio. It is the denominator of drawdown percentage; holding it fixed would
  make a $100 position 100% of capital and report drawdowns that describe
  leverage rather than the strategy.

Everything expressed as a percentage — stop loss, take profit, slippage cap —
is already size-invariant and is left alone. So across the four runs the only
thing that genuinely changes is **how much fixed cost each trade carries**,
which is exactly the variable under test.

This changes no default. `RiskConfig`'s own defaults and the soft ceiling are
untouched; these are research parameters, and the $25/$100 runs set
`position_size_override_ack` explicitly — the friction CLAUDE.md rule 6 asks
for, working as intended.

Regime detection is **not** re-run: see rule 5 of the record. Entry timing does
not depend on size, so its empty trend arm is empty at every size.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.runner import BacktestRunner  # noqa: E402
from core.config import load_config  # noqa: E402
from core.performance import MIN_POOLED_TRADES, net_pnl  # noqa: E402
from execution.candle_cache import CandleCache  # noqa: E402
from strategy.strategy_momentum import MomentumParams, MomentumStrategy  # noqa: E402

from sweep import MIN_TRADES, combinations, score, split_candles  # noqa: E402
from walk_forward import baseline_folds, judge  # noqa: E402

SIZES = [Decimal("5"), Decimal("10"), Decimal("25"), Decimal("100")]
HURDLE = {  # per round trip, from the committed record
    Decimal("5"): "0.47%", Decimal("10"): "0.35%",
    Decimal("25"): "0.27%", Decimal("100"): "0.23%",
}
INTERVALS = ["1h", "4h", "15m"]
FOLDS = 3


def at_size(config, size: Decimal):
    """The same config with only the size-denominated settings rescaled."""
    risk = config.risk.model_copy(update={
        "position_size_usd": size,
        "daily_loss_limit_usd": size * 2,
        "position_size_override_ack": True,
    })
    backtest = config.backtest.model_copy(update={"initial_capital_usd": size * 10})
    return config.model_copy(update={"risk": risk, "backtest": backtest})


def buy_and_hold_net(config, candles, size: Decimal) -> Decimal:
    """One round trip: buy the first close, sell the last, full costs.

    Recomputed at every size per rule 3 — the benchmark scales with capital
    too, and holding it at its $10 value would flatter the strategy.
    """
    from execution.costs import CostModel, sol_price_from_close

    model = CostModel(config.costs)
    token = config.strategy.token_mints[0]
    adverse = config.backtest.total_adverse_pct / Decimal(100)
    entry = candles[0].close * (Decimal(1) + adverse)
    exit_ = candles[-1].close * (Decimal(1) - adverse)
    fees = (
        model.estimate(size, creates_token_account=True,
                       sol_price_usd=sol_price_from_close(token, candles[0].close)).total_usd
        + model.estimate(size, creates_token_account=False,
                         sol_price_usd=sol_price_from_close(token, candles[-1].close)).total_usd
    )
    return size * (exit_ - entry) / entry - fees


def run_defaults(config, cache, size: Decimal) -> list[dict]:
    """Round 2: cost-corrected runs at default parameters."""
    token = config.strategy.token_mints[0]
    rows = []
    for interval in INTERVALS:
        candles = cache.load(config.paper.pool_address, interval)
        result = BacktestRunner(config, MomentumStrategy(MomentumParams())).run(token, candles)
        rows.append({
            "interval": interval,
            "net": result.net_pnl_usd,
            "trades": result.trade_count,
            "dd_pct": result.max_drawdown_pct,
            "dd_usd": result.max_drawdown_pct / Decimal(100) * config.backtest.initial_capital_usd,
            "bh": buy_and_hold_net(config, candles, size),
        })
    return rows


def run_holdout(config, cache, size: Decimal) -> list[dict]:
    """Round 1: tune on the 70% split, score the winner on the held-out 30%."""
    token = config.strategy.token_mints[0]
    rows = []
    for interval in INTERVALS:
        candles = cache.load(config.paper.pool_address, interval)
        tuning, holdout = split_candles(candles)
        scored = [(p, score(config, tuning, p, token)) for p in combinations()]
        eligible = [(p, s) for p, s in scored if s["trades"] >= MIN_TRADES]
        if not eligible:
            rows.append({"interval": interval, "eligible": False})
            continue
        best_params, best_tune = max(eligible, key=lambda ps: ps[1]["expectancy"])
        held = score(config, holdout, best_params, token)
        rows.append({
            "interval": interval, "eligible": True, "params": best_params,
            "tune_net": best_tune["net"], "net": held["net"], "trades": held["trades"],
            "dd_pct": held["max_dd"],
            "dd_usd": held["max_dd"] / Decimal(100) * config.backtest.initial_capital_usd,
            "bh": buy_and_hold_net(config, holdout, size),
        })
    return rows


def run_phase_a(config, cache, size: Decimal) -> list[dict]:
    """Round 3: walk-forward at default parameters, judged on the locked rule."""
    token = config.strategy.token_mints[0]
    rows = []
    for interval in INTERVALS:
        candles = cache.load(config.paper.pool_address, interval)
        result = BacktestRunner(config, MomentumStrategy(MomentumParams())).run(token, candles)
        folds = baseline_folds(result, candles, FOLDS)
        verdict = judge(folds)
        pooled = sum((f.net for f in folds), Decimal(0))
        biggest = max((f.net for f in folds), default=Decimal(0))
        rows.append({
            "interval": interval, "pooled": pooled,
            "folds": [f.net for f in folds],
            "trades": sum(f.trade_count for f in folds),
            "replicated": verdict.replicated,
            "concentration": (biggest / pooled * 100) if pooled > 0 else None,
            "dd_pct": result.max_drawdown_pct,
            "dd_usd": result.max_drawdown_pct / Decimal(100) * config.backtest.initial_capital_usd,
            "bh": buy_and_hold_net(config, candles, size),
        })
    return rows


def main() -> int:
    base = load_config("config.backtest.yaml", env={})
    cache = CandleCache(base.data.cache_dir)

    print("CAPITAL-RANGE SENSITIVITY")
    print("Rule: planning/decisions/2026-09-13-capital-range-sensitivity.md (committed first)")
    print("A flip counts as fee-driven ONLY if it tracks the hurdle curve.")
    print("Still negative at $100 => the signal has no edge, not a capital problem.\n")

    for label, runner in (
        ("ROUND 2 — cost-corrected, default parameters", run_defaults),
        ("ROUND 3 — walk-forward Phase A", run_phase_a),
        ("ROUND 1 — sweep, held-out", run_holdout),
    ):
        print("=" * 78)
        print(label)
        print("=" * 78)
        for size in SIZES:
            config = at_size(base, size)
            print(f"\n  ${size} position (hurdle {HURDLE[size]}, "
                  f"daily limit ${size * 2}, capital ${size * 10})")
            for row in runner(config, cache, size):
                if row.get("eligible") is False:
                    print(f"    {row['interval']:<4} NO ELIGIBLE CONFIGURATION")
                    continue
                flip = "POSITIVE" if row["net"] > 0 else "negative"
                beats = "beats B&H" if row["net"] > row["bh"] else "loses to B&H"
                extra = ""
                if "replicated" in row:
                    extra = f"  replicated={row['replicated']}"
                    if row["concentration"] is not None:
                        extra += f"  top fold {row['concentration']:.0f}% of pooled"
                print(f"    {row['interval']:<4} net {row['net']:+9.4f}  "
                      f"{flip:<8} {beats:<13} trades {row['trades']:>3}  "
                      f"maxDD {row['dd_pct']:>5.2f}% (${row['dd_usd']:.2f})  "
                      f"B&H {row['bh']:+8.4f}{extra}")
        print()

    print("=" * 78)
    print("ROUND 6 — regime detection: SIZE-INVARIANT, not re-run")
    print("=" * 78)
    print("  Its refutation was that 1 trade in 59 entered a trend-labelled bar.")
    print("  Entry timing does not depend on position size, so the trend arm is")
    print("  empty at $5 and empty at $100. Re-running would produce four identical")
    print("  empty arms and dress a non-result as coverage. See rule 5 of the record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
