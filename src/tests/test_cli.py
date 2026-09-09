"""CLI — especially that `live` refuses and says why."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import cli
from tests.test_gate import VALID_GATE

TOKEN = "So11111111111111111111111111111111111111112"
POOL = "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj"


def write_config(tmp_path: Path, mode: str, **overrides) -> Path:
    data = {
        "mode": mode,
        "risk": {
            "position_size_usd": 10,
            "max_slippage_pct": 0.5,
            "daily_loss_limit_usd": 20,
            "per_trade_stop_loss_pct": 5,
            "per_trade_take_profit_pct": 10,
        },
        "strategy": {"name": "momentum", "token_mints": [TOKEN]},
        "paper": {"pool_address": POOL},
        "state_dir": str(tmp_path / "state"),
        "gate_file": str(tmp_path / "gate.json"),
        **overrides,
    }
    path = tmp_path / f"config.{mode}.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_parser_exposes_all_four_commands():
    parser = cli.build_parser()

    for command in ("backtest", "paper", "live", "gate"):
        assert parser.parse_args([command]).command == command


def test_no_command_is_an_error():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_live_refuses_when_the_gate_is_absent(tmp_path, capsys):
    config = write_config(tmp_path, "live")

    exit_code = cli.main(["live", "--config", str(config)])

    assert exit_code == cli.EXIT_GATE_LOCKED
    assert "LOCKED" in capsys.readouterr().err


def test_live_refusal_explains_where_to_look(tmp_path, capsys):
    config = write_config(tmp_path, "live")

    cli.main(["live", "--config", str(config)])

    err = capsys.readouterr().err
    assert "mvp_spec.md" in err
    assert "live-gate.example.json" in err


def test_live_refuses_on_a_partially_satisfied_gate(tmp_path, capsys):
    config = write_config(tmp_path, "live")
    (tmp_path / "gate.json").write_text(
        json.dumps({**VALID_GATE, "net_expectancy_usd": -1})
    )

    exit_code = cli.main(["live", "--config", str(config)])

    assert exit_code == cli.EXIT_GATE_LOCKED
    assert "not positive" in capsys.readouterr().err


def test_live_still_sends_nothing_even_when_the_gate_passes(tmp_path, capsys):
    """Stage 6 is not built; saying so beats a stub that looks like it traded."""
    config = write_config(tmp_path, "live")
    (tmp_path / "gate.json").write_text(json.dumps(VALID_GATE))

    exit_code = cli.main(["live", "--config", str(config)])

    err = capsys.readouterr().err
    assert exit_code == cli.EXIT_ERROR
    assert "No orders were sent" in err


def test_gate_command_reports_each_failure(tmp_path, capsys):
    config = write_config(tmp_path, "paper")

    exit_code = cli.main(["gate", "--config", str(config)])

    out = capsys.readouterr().out
    assert exit_code == cli.EXIT_GATE_LOCKED
    assert "LOCKED" in out


def test_gate_command_succeeds_when_unlocked(tmp_path, capsys):
    config = write_config(tmp_path, "paper")
    (tmp_path / "gate.json").write_text(json.dumps(VALID_GATE))

    exit_code = cli.main(["gate", "--config", str(config)])

    assert exit_code == cli.EXIT_OK
    assert "unlocked" in capsys.readouterr().out


def test_missing_token_is_a_clear_error(tmp_path):
    config = write_config(tmp_path, "paper", strategy={"name": "momentum", "token_mints": []})

    with pytest.raises(SystemExit, match="no token configured"):
        cli.main(["paper", "--config", str(config)])


def test_multiple_tokens_are_refused_in_v01(tmp_path):
    config = write_config(
        tmp_path, "paper", strategy={"name": "momentum", "token_mints": [TOKEN, "Other"]}
    )

    with pytest.raises(SystemExit, match="single token"):
        cli.main(["paper", "--config", str(config)])


def test_missing_pool_is_a_clear_error(tmp_path):
    config = write_config(tmp_path, "paper", paper={"pool_address": ""})

    with pytest.raises(SystemExit, match="no pool configured"):
        cli.main(["paper", "--config", str(config)])


class FakeGeckoTerminal:
    """Stands in for the network client the CLI builds internally."""

    series: list = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def fetch_candles(self, pool_address, interval="15m", limit=100):
        return list(FakeGeckoTerminal.series)


class FakeJupiter:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def get_quote(self, **kwargs):
        from decimal import Decimal

        from execution.mock import MockQuoteSource

        return MockQuoteSource(slippage_pct=Decimal("0.2")).get_quote(**kwargs)


@pytest.fixture
def offline_cli(monkeypatch, tmp_path):
    """Point the CLI's own clients at fakes, and isolate the candle cache."""
    from datetime import datetime, timedelta, timezone
    from decimal import Decimal

    from core.types import Candle

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    prices = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96, 102, 110, 120, 118, 105]
    FakeGeckoTerminal.series = [
        Candle(
            timestamp=start + timedelta(minutes=15 * i),
            open=Decimal(str(p)),
            high=Decimal(str(p)),
            low=Decimal(str(p)),
            close=Decimal(str(p)),
            volume=Decimal("1000"),
        )
        for i, p in enumerate(prices)
    ]
    monkeypatch.setattr(cli, "GeckoTerminalClient", FakeGeckoTerminal)
    monkeypatch.setattr(cli, "JupiterQuoteClient", FakeJupiter)
    return tmp_path


def test_backtest_command_runs_and_prints_net(offline_cli, capsys):
    config = write_config(
        offline_cli,
        "backtest",
        data={"cache_dir": str(offline_cli / "cache"), "candle_interval": "15m"},
        strategy={
            "name": "momentum",
            "token_mints": [TOKEN],
            "params": {"fast_ema": 3, "slow_ema": 6, "rsi_period": 5},
        },
    )

    exit_code = cli.main(["backtest", "--config", str(config)])

    assert exit_code == cli.EXIT_OK
    assert "NET=" in capsys.readouterr().out


def test_backtest_command_writes_a_report(offline_cli, capsys):
    config = write_config(
        offline_cli,
        "backtest",
        data={"cache_dir": str(offline_cli / "cache"), "candle_interval": "15m"},
        strategy={
            "name": "momentum",
            "token_mints": [TOKEN],
            "params": {"fast_ema": 3, "slow_ema": 6, "rsi_period": 5},
        },
    )
    reports = offline_cli / "reports"

    cli.main(
        [
            "backtest",
            "--config", str(config),
            "--report", "cli-test",
            "--report-dir", str(reports),
        ]
    )

    written = list(reports.glob("*.md"))
    assert len(written) == 1
    assert "Net P&L" in written[0].read_text()


def test_paper_command_runs_a_single_tick(offline_cli, capsys):
    config = write_config(
        offline_cli,
        "paper",
        data={"cache_dir": str(offline_cli / "cache"), "candle_interval": "15m"},
        strategy={
            "name": "momentum",
            "token_mints": [TOKEN],
            "params": {"fast_ema": 3, "slow_ema": 6, "rsi_period": 5},
        },
    )

    exit_code = cli.main(["paper", "--config", str(config), "--once"])

    out = capsys.readouterr().out
    assert exit_code == cli.EXIT_OK
    assert "paper session" in out
    assert "of 30" in out


def test_paper_command_persists_across_invocations(offline_cli):
    config = write_config(
        offline_cli,
        "paper",
        data={"cache_dir": str(offline_cli / "cache"), "candle_interval": "15m"},
        strategy={
            "name": "momentum",
            "token_mints": [TOKEN],
            "params": {"fast_ema": 3, "slow_ema": 6, "rsi_period": 5},
        },
    )

    cli.main(["paper", "--config", str(config), "--once"])
    cli.main(["paper", "--config", str(config), "--once"])

    from paper.session import PaperSessionStore

    state = PaperSessionStore(offline_cli / "state").load()
    assert state.ticks == 2


def test_shipped_configs_drive_the_cli(tmp_path):
    """The configs in the repo must actually be usable by the CLI."""
    root = Path(__file__).resolve().parents[2]
    from core.config import load_config

    for name in ("config.backtest.yaml", "config.paper.yaml", "config.live.yaml"):
        config = load_config(root / name, env={})
        assert config.strategy.token_mints
        assert config.paper.pool_address
