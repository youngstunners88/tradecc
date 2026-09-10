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


class PaperConfig(StrictModel):
    """Paper-mode wiring: what to poll, and what to price against.

    Paper mode uses real quotes, so it needs a real quote asset and a real
    pool to read candles from. Nothing here can cause a send.
    """

    # USDC on Solana — the asset positions are denominated in.
    quote_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    quote_mint_decimals: int = 6
    # GeckoTerminal pool address for candle polling.
    pool_address: str = ""
    poll_seconds: int = 300

    @field_validator("quote_mint_decimals", "poll_seconds")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value


class BacktestConfig(StrictModel):
    """Backtest-only assumptions.

    Adverse price movement is split into two components because they have
    different epistemic status, and collapsing them into one number hid
    that difference:

    - `price_impact_pct` is **calibrated from measurement**. Jupiter's
      quote reports `priceImpactPct` for a real size on a real route;
      `research/calibrate_costs.py` samples it and prints the value to
      put here. It is still applied as a constant to historical bars —
      history carries no quotes — but it is a measured constant rather
      than an invented one.
    - `execution_slippage_pct` is **still an assumption**: drift between
      the quote and the fill, which no historical measurement can supply.
      A momentum strategy buys into rising prices, so this is adverse by
      construction and the default stays deliberately pessimistic.

    Keeping them separate means "how much of this is measured?" has an
    answer at a glance. Fills use the sum, always applied adversely.
    """

    initial_capital_usd: Decimal = Decimal("100")
    # Measured 2026-09-10: SOL/USDC impact was 0.0000%–0.0012% across
    # $5–$200. Rounded up to 0.01% rather than modelled as free.
    price_impact_pct: Decimal = Decimal("0.01")
    execution_slippage_pct: Decimal = Decimal("0.10")

    @property
    def total_adverse_pct(self) -> Decimal:
        """Total adverse move per side — what a fill is actually marked at."""
        return self.price_impact_pct + self.execution_slippage_pct

    @field_validator(
        "initial_capital_usd",
        "price_impact_pct",
        "execution_slippage_pct",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"not a valid decimal: {value!r}") from exc

    @field_validator("initial_capital_usd")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator("price_impact_pct", "execution_slippage_pct")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        # Zero is legitimate here — a deep pool genuinely measures at zero
        # impact — but negative would mean fills improve on the quote.
        if value < 0:
            raise ValueError("must not be negative")
        return value


class CostsConfig(StrictModel):
    """Fixed-cost parameters for fill simulation.

    Defaults are deliberately pessimistic. Understating costs produces a
    paper run that clears the validation gate and then loses money live,
    which is the most expensive possible failure mode for this project.
    """

    base_fee_lamports: int = 5000
    # Priority fees are quoted **per compute unit**, not as a flat total.
    # Modelling them as a flat total understated them by roughly the size
    # of the CU limit — five orders of magnitude — which is why this is
    # now two fields that must be multiplied.
    compute_unit_limit: int = 200_000
    priority_fee_microlamports_per_cu: int = 200_000
    # Jito tip for MEV-protected routing, which Solana swaps typically
    # need and which was previously modelled as zero. Default is the
    # landed-tip 75th percentile measured 2026-09-10 via
    # https://bundles.jito.wtf/api/v1/bundles/tip_floor — refresh with
    # research/calibrate_costs.py.
    jito_tip_lamports: int = 17_392
    # Rent-exempt minimum for an SPL associated token account.
    ata_rent_lamports: int = 2_039_280
    platform_fee_bps: int = 0
    # Fallback only. A hardcoded market price is wrong the day after it is
    # written — this one said 200 while SOL traded at ~102. Prefer passing
    # a live or per-bar price to `CostModel.estimate(sol_price_usd=...)`;
    # this value is what remains when no price source is available.
    sol_price_usd: Decimal = Decimal("200")

    @field_validator("sol_price_usd", mode="before")
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"not a valid decimal: {value!r}") from exc

    @field_validator("sol_price_usd")
    @classmethod
    def _price_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator(
        "base_fee_lamports",
        "priority_fee_microlamports_per_cu",
        "jito_tip_lamports",
        "ata_rent_lamports",
        "platform_fee_bps",
    )
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must not be negative")
        return value

    @field_validator("compute_unit_limit")
    @classmethod
    def _cu_limit_positive(cls, value: int) -> int:
        # A zero CU limit would silently zero the priority fee, which is
        # the exact bug this field was added to fix.
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value


class ProvidersConfig(StrictModel):
    """External provider endpoints and their client-side rate limits.

    Every one of these is a free tier, so every one gets limited on our
    side. Limits are configured, never assumed — see the decision record
    `planning/decisions/2026-09-09-stage2-provider-tiers.md`.
    """

    # Jupiter's free public host. `api.jup.ag` is the keyed tier; switching
    # to it is a deliberate config change, not a silent fallback.
    jupiter_base_url: str = "https://lite-api.jup.ag"
    jupiter_max_requests_per_minute: int = 60

    helius_base_url: str = "https://mainnet.helius-rpc.com"
    helius_max_requests_per_minute: int = 60

    @field_validator("jupiter_max_requests_per_minute", "helius_max_requests_per_minute")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator("jupiter_base_url", "helius_base_url")
    @classmethod
    def _must_be_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("provider base URL must use https")
        return value.rstrip("/")


class RunConfig(StrictModel):
    mode: Mode
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    costs: CostsConfig = Field(default_factory=CostsConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    paper: PaperConfig = Field(default_factory=PaperConfig)
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
