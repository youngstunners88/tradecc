"""TradeCC command line.

Three subcommands matching the three run modes. `live` is not a mode you
can simply select: it checks the validation gate and refuses, and the
risk engine re-checks it on every intent behind that.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from backtest.report import write_report
from backtest.runner import BacktestRunner
from core.config import RunConfig, load_config
from core.gate import evaluate_live_gate
from core.logging import configure_logging, get_logger, register_secret
from core.telemetry import configure_telemetry, log_and_track
from core.types import Mode
from execution.candle_cache import CandleCache
from execution.geckoterminal import GeckoTerminalClient
from execution.jupiter import JupiterQuoteClient
from paper.session import PaperSessionStore
from paper.trader import PaperTrader
from strategy.registry import build_strategy

logger = get_logger("tradecc.cli")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_GATE_LOCKED = 2


def _bootstrap(config_path: str, mode: Mode | None) -> RunConfig:
    configure_logging()
    configure_telemetry()
    config = load_config(config_path, mode=mode)
    # Register secrets with the log scrubber before anything can log them.
    for name in ("HELIUS_API_KEY", "POSTHOG_API_KEY", "OPENROUTER_API_KEY"):
        register_secret(os.environ.get(name))
    return config


def _resolve_token(config: RunConfig) -> str:
    if not config.strategy.token_mints:
        raise SystemExit(
            "no token configured: set strategy.token_mints in the config file"
        )
    if len(config.strategy.token_mints) > 1:
        raise SystemExit(
            "v0.1 trades a single token; strategy.token_mints has "
            f"{len(config.strategy.token_mints)}"
        )
    return config.strategy.token_mints[0]


def cmd_backtest(args: argparse.Namespace) -> int:
    config = _bootstrap(args.config, Mode.BACKTEST)
    token = _resolve_token(config)
    if not config.paper.pool_address:
        raise SystemExit("no pool configured: set paper.pool_address in the config file")

    strategy = build_strategy(config.strategy)
    cache = CandleCache(config.data.cache_dir)
    client = GeckoTerminalClient(config.data)
    candles = cache.load_or_fetch(
        config.paper.pool_address,
        config.data.candle_interval,
        lambda: client.fetch_candles(
            config.paper.pool_address, config.data.candle_interval, limit=args.limit
        ),
        refresh=args.refresh,
    )

    result = BacktestRunner(config, strategy).run(token, candles)
    print(_format_summary(result))

    if args.report:
        path = write_report(
            result,
            dict(config.strategy.params),
            data_source=config.data.source,
            interval=config.data.candle_interval,
            output_dir=args.report_dir,
            summary=args.report,
        )
        print(f"report: {path}")
    return EXIT_OK


def cmd_paper(args: argparse.Namespace) -> int:
    config = _bootstrap(args.config, Mode.PAPER)
    token = _resolve_token(config)
    if not config.paper.pool_address:
        raise SystemExit("no pool configured: set paper.pool_address in the config file")

    strategy = build_strategy(config.strategy)
    store = PaperSessionStore(config.state_dir)
    state = store.load_or_start(
        token_mint=token,
        strategy_name=strategy.name,
        initial_capital_usd=config.backtest.initial_capital_usd,
    )
    trader = PaperTrader(
        config=config,
        strategy=strategy,
        quote_source=JupiterQuoteClient(config.providers),
        candle_source=GeckoTerminalClient(config.data),
        store=store,
    )

    log_and_track("mode.changed", from_mode="none", to_mode=Mode.PAPER.value, gate_passed=False)
    print(
        f"paper session: {token} · started {state.started_at.isoformat()} · "
        f"day {state.elapsed_days():.1f} of 30 · {state.trade_count} trades"
    )

    # None means run indefinitely; --once is shorthand for a single tick.
    max_ticks = args.ticks if args.ticks else (1 if args.once else None)
    completed = 0
    while max_ticks is None or completed < max_ticks:
        result = trader.run_tick_and_save(state)
        print(f"[{result.at.isoformat()}] {result.action} {result.detail}".rstrip())
        if result.error:
            print(f"  (continuing; provider error: {result.error})", file=sys.stderr)
        completed += 1
        if max_ticks is not None and completed >= max_ticks:
            break
        time.sleep(config.paper.poll_seconds)

    print(_format_session(state))
    return EXIT_OK


def cmd_live(args: argparse.Namespace) -> int:
    """Live mode refuses unless the validation gate is fully satisfied."""
    config = _bootstrap(args.config, Mode.LIVE)
    gate = evaluate_live_gate(config.gate_file)

    log_and_track(
        "mode.changed",
        from_mode="none",
        to_mode=Mode.LIVE.value,
        gate_passed=gate.unlocked,
    )

    if not gate.unlocked:
        print(gate.describe(), file=sys.stderr)
        print(
            "\nLive trading is locked. See planning/specs/mvp_spec.md for the gate, "
            "and ops/live-gate.example.json for the file it reads.",
            file=sys.stderr,
        )
        return EXIT_GATE_LOCKED

    # The gate is satisfied, but live execution is Stage 6 and does not
    # exist yet. Saying so plainly beats a stub that looks like it traded.
    print(
        "Live gate is satisfied, but live execution is not implemented "
        "(Stage 6). No orders were sent.",
        file=sys.stderr,
    )
    return EXIT_ERROR


def cmd_gate(args: argparse.Namespace) -> int:
    config = _bootstrap(args.config, None)
    gate = evaluate_live_gate(config.gate_file)
    print(gate.describe())
    for failure in gate.failures:
        print(f"  - {failure}")
    return EXIT_OK if gate.unlocked else EXIT_GATE_LOCKED


def _format_summary(result) -> str:
    return (
        f"trades={result.trade_count} "
        f"gross={result.gross_pnl_usd:.4f} "
        f"fees={result.total_fees_usd:.4f} "
        f"NET={result.net_pnl_usd:.4f} "
        f"expectancy={result.expectancy_usd:.4f}/trade "
        f"win_rate={result.win_rate_pct:.1f}% "
        f"maxDD={result.max_drawdown_pct:.2f}%"
    )


def _format_session(state) -> str:
    return (
        f"day {state.elapsed_days():.1f}/30 · trades={state.trade_count} "
        f"gross={state.gross_pnl_usd:.4f} fees={state.total_fees_usd:.4f} "
        f"NET={state.net_pnl_usd:.4f} expectancy={state.expectancy_usd:.4f}/trade "
        f"maxDD={state.max_drawdown_pct:.2f}%"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradecc", description="Solana momentum trading bot (paper-trading first)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="run the strategy over historical candles")
    backtest.add_argument("--config", default="config.backtest.yaml")
    backtest.add_argument("--limit", type=int, default=1000, help="candles to fetch")
    backtest.add_argument("--refresh", action="store_true", help="bypass the candle cache")
    backtest.add_argument("--report", help="write a report with this summary slug")
    backtest.add_argument("--report-dir", default="research/backtests")
    backtest.set_defaults(func=cmd_backtest)

    paper = subparsers.add_parser("paper", help="paper trade against real quotes (sends nothing)")
    paper.add_argument("--config", default="config.paper.yaml")
    paper.add_argument("--ticks", type=int, help="stop after N ticks (default: run forever)")
    paper.add_argument("--once", action="store_true", help="run a single tick and exit")
    paper.set_defaults(func=cmd_paper)

    live = subparsers.add_parser("live", help="live trading (gated; refuses unless validated)")
    live.add_argument("--config", default="config.live.yaml")
    live.set_defaults(func=cmd_live)

    gate = subparsers.add_parser("gate", help="report live-gate status and why it is locked")
    gate.add_argument("--config", default="config.paper.yaml")
    gate.set_defaults(func=cmd_gate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
