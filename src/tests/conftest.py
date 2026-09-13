from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from core.config import DataConfig, RiskConfig, RunConfig, StrategyConfig
from core.types import Mode, Quote, Signal, SignalType, Side, TradeIntent
from risk.state import RiskStateStore

TOKEN = "So11111111111111111111111111111111111111112"


@pytest.fixture
def risk_config() -> RiskConfig:
    return RiskConfig(
        position_size_usd=Decimal("10"),
        max_slippage_pct=Decimal("0.5"),
        daily_loss_limit_usd=Decimal("20"),
        per_trade_stop_loss_pct=Decimal("5"),
        per_trade_take_profit_pct=Decimal("10"),
    )


@pytest.fixture
def run_config(tmp_path: Path, risk_config: RiskConfig) -> RunConfig:
    return RunConfig(
        mode=Mode.PAPER,
        risk=risk_config,
        strategy=StrategyConfig(),
        data=DataConfig(),
        state_dir=tmp_path / "state",
        gate_file=tmp_path / "live-gate.json",
    )


@pytest.fixture
def store(tmp_path: Path) -> RiskStateStore:
    return RiskStateStore(tmp_path / "state")


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def make_quote(
    expected: str = "100",
    worst_case: str = "100.2",
    amount_usd: str = "10",
    side: Side = Side.BUY,
) -> Quote:
    return Quote(
        token_mint=TOKEN,
        side=side,
        amount_usd=Decimal(amount_usd),
        expected_price=Decimal(expected),
        worst_case_price=Decimal(worst_case),
        fee_usd=Decimal("0.02"),
        source="mock",
    )


def make_intent(
    quote: Quote | None = None,
    size_usd: str = "10",
    mode: Mode = Mode.PAPER,
    at: datetime | None = None,
) -> TradeIntent:
    timestamp = at or datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    return TradeIntent(
        signal=Signal(
            type=SignalType.BUY,
            token_mint=TOKEN,
            price=Decimal("100"),
            timestamp=timestamp,
            strategy="momentum",
        ),
        quote=quote or make_quote(),
        size_usd=Decimal(size_usd),
        mode=mode,
    )
