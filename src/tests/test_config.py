from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from core.config import RiskConfig, load_config
from core.types import Mode

BASE = {
    "mode": "paper",
    "risk": {
        "position_size_usd": 10,
        "max_slippage_pct": 0.5,
        "daily_loss_limit_usd": 20,
        "per_trade_stop_loss_pct": 5,
        "per_trade_take_profit_pct": 10,
    },
}


def write_config(path: Path, **overrides) -> Path:
    path.write_text(yaml.safe_dump({**BASE, **overrides}))
    return path


def test_loads_valid_config(tmp_path):
    config = load_config(write_config(tmp_path / "c.yaml"), env={})

    assert config.mode is Mode.PAPER
    assert config.risk.position_size_usd == Decimal("10")


def test_decimals_are_exact_not_float(tmp_path):
    config = load_config(write_config(tmp_path / "c.yaml"), env={})

    # Decimal("0.5") from str, not Decimal(0.5) from a binary float.
    assert config.risk.max_slippage_pct == Decimal("0.5")
    assert str(config.risk.max_slippage_pct) == "0.5"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "absent.yaml", env={})


def test_explicit_mode_argument_wins(tmp_path):
    config = load_config(
        write_config(tmp_path / "c.yaml"), mode=Mode.BACKTEST, env={"BOT_MODE": "paper"}
    )

    assert config.mode is Mode.BACKTEST


def test_env_mode_overrides_file(tmp_path):
    config = load_config(write_config(tmp_path / "c.yaml"), env={"BOT_MODE": "backtest"})

    assert config.mode is Mode.BACKTEST


def test_invalid_env_mode_raises(tmp_path):
    with pytest.raises(ValueError, match="not a valid mode"):
        load_config(write_config(tmp_path / "c.yaml"), env={"BOT_MODE": "yolo"})


def test_missing_mode_everywhere_raises(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump({"risk": BASE["risk"]}))

    with pytest.raises(ValueError, match="run mode not set"):
        load_config(path, env={})


def test_oversized_position_needs_explicit_acknowledgement():
    with pytest.raises(ValidationError, match="ceiling"):
        RiskConfig(position_size_usd=Decimal("500"))


def test_oversized_position_allowed_with_acknowledgement():
    config = RiskConfig(
        position_size_usd=Decimal("500"),
        daily_loss_limit_usd=Decimal("100"),
        position_size_override_ack=True,
    )

    assert config.position_size_usd == Decimal("500")


def test_stop_loss_larger_than_daily_limit_is_rejected():
    """A stop bigger than the daily budget would breach before the breaker fires."""
    with pytest.raises(ValidationError, match="daily"):
        RiskConfig(
            position_size_usd=Decimal("10"),
            per_trade_stop_loss_pct=Decimal("50"),
            daily_loss_limit_usd=Decimal("1"),
        )


@pytest.mark.parametrize(
    "field",
    [
        "position_size_usd",
        "max_slippage_pct",
        "daily_loss_limit_usd",
        "per_trade_stop_loss_pct",
        "per_trade_take_profit_pct",
    ],
)
def test_non_positive_risk_values_are_rejected(field):
    with pytest.raises(ValidationError):
        RiskConfig(**{field: Decimal("0")})


def test_unknown_config_keys_are_rejected():
    """A typo'd risk limit must fail loudly, not be silently ignored."""
    with pytest.raises(ValidationError):
        RiskConfig(max_slipage_pct=Decimal("5"))


def test_shipped_configs_are_valid():
    root = Path(__file__).resolve().parents[2]
    for name in ("config.backtest.yaml", "config.paper.yaml", "config.live.yaml"):
        assert load_config(root / name, env={}).risk.position_size_usd <= Decimal("10")
