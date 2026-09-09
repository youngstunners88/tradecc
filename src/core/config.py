"""Configuration loading and validation.

Config comes from two places: a per-mode YAML file for strategy/risk
parameters, and environment variables for secrets and the run mode.
Secrets never appear in YAML.

Validation is deliberately strict and fails at startup rather than at the
first trade. A bot that discovers its risk limits are malformed halfway
through a session has already taken positions under limits nobody checked.
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.types import Mode

# Rule 6 in CLAUDE.md: position sizing defaults to $5–$10 and must not be
# silently scaled up. Exceeding this ceiling requires an explicit
# acknowledgement in config — it is not enough to just type a bigger number.
DEFAULT_POSITION_SIZE_USD = Decimal("10")
POSITION_SIZE_SOFT_CEILING_USD = Decimal("10")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RiskConfig(StrictModel):
    """Risk limits. Every field here is load-bearing — see CLAUDE.md rule 4."""

    position_size_usd: Decimal = DEFAULT_POSITION_SIZE_USD
    max_slippage_pct: Decimal = Decimal("0.5")
    daily_loss_limit_usd: Decimal = Decimal("20")
    per_trade_stop_loss_pct: Decimal = Decimal("5")
    per_trade_take_profit_pct: Decimal = Decimal("10")

    # Must be set to true to run a position size above the $10 soft ceiling.
    # Its only purpose is to make scaling up a deliberate, visible act.
    position_size_override_ack: bool = False

    @field_validator(
        "position_size_usd",
        "max_slippage_pct",
        "daily_loss_limit_usd",
        "per_trade_stop_loss_pct",
        "per_trade_take_profit_pct",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal:
        # Route through str so YAML floats (0.5 -> 0.5000000000000000277…)
        # do not smuggle binary rounding error into a risk threshold.
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"not a valid decimal: {value!r}") from exc

    @field_validator(
        "position_size_usd",
        "max_slippage_pct",
        "daily_loss_limit_usd",
        "per_trade_stop_loss_pct",
        "per_trade_take_profit_pct",
    )
    @classmethod
    def _must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @model_validator(mode="after")
    def _enforce_position_size_ceiling(self) -> RiskConfig:
        if (
            self.position_size_usd > POSITION_SIZE_SOFT_CEILING_USD
            and not self.position_size_override_ack
        ):
            raise ValueError(
                f"position_size_usd={self.position_size_usd} exceeds the "
                f"${POSITION_SIZE_SOFT_CEILING_USD} ceiling. This is intentional "
                "friction (CLAUDE.md rule 6): set position_size_override_ack: true "
                "to confirm you meant to scale up."
            )
        return self

    @model_validator(mode="after")
    def _stop_loss_must_fit_daily_limit(self) -> RiskConfig:
        max_single_trade_loss = self.position_size_usd * self.per_trade_stop_loss_pct / Decimal(100)
        if max_single_trade_loss > self.daily_loss_limit_usd:
            raise ValueError(
                f"a single stop-loss ({max_single_trade_loss} USD) exceeds the daily "
                f"loss limit ({self.daily_loss_limit_usd} USD), so the circuit breaker "
                "could never fire before a trade already breached it"
            )
        return self


class StrategyConfig(StrictModel):
    name: str = "momentum"
    # Strategy parameters stay untyped here on purpose — each strategy module
    # validates its own params, so adding a strategy does not touch this file.
    params: dict[str, Any] = Field(default_factory=dict)
    token_mints: tuple[str, ...] = ()


class DataConfig(StrictModel):
    source: str = "geckoterminal"
    cache_dir: Path = Path("research/.candle-cache")
    max_requests_per_minute: int = 30
    candle_interval: str = "15m"

    @field_validator("max_requests_per_minute")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value


class RunConfig(StrictModel):
    mode: Mode
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    state_dir: Path = Path("ops/.state")
    gate_file: Path = Path("ops/live-gate.json")


def load_config(
    config_path: Path | str,
    mode: Mode | None = None,
    env: dict[str, str] | None = None,
) -> RunConfig:
    """Load and validate config from a YAML file.

    `mode` overrides the file's mode when given; otherwise BOT_MODE from the
    environment wins, then the file's own value. Mode is resolved explicitly
    rather than defaulted so nothing can drift into `live` by accident.
    """
    env = os.environ if env is None else env
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config file must contain a YAML mapping: {path}")

    resolved = mode or _mode_from_env(env) or raw.get("mode")
    if resolved is None:
        raise ValueError(
            "run mode not set. Pass mode=, set BOT_MODE, or add `mode:` to the config file."
        )
    raw["mode"] = Mode(resolved)
    return RunConfig(**raw)


def _mode_from_env(env: dict[str, str]) -> Mode | None:
    value = env.get("BOT_MODE")
    if not value:
        return None
    try:
        return Mode(value.strip().lower())
    except ValueError as exc:
        valid = ", ".join(m.value for m in Mode)
        raise ValueError(f"BOT_MODE={value!r} is not a valid mode (expected: {valid})") from exc
