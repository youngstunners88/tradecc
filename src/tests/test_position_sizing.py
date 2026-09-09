from __future__ import annotations

from decimal import Decimal

import pytest

from core.config import RiskConfig
from core.types import RejectionCode
from risk.position_sizing import check_position_size, resolve_position_size


def test_default_size_is_within_the_five_to_ten_band():
    assert Decimal("5") <= resolve_position_size(RiskConfig()) <= Decimal("10")


def test_approves_configured_size(risk_config):
    assert check_position_size(Decimal("10"), risk_config).approved


def test_approves_smaller_than_configured(risk_config):
    assert check_position_size(Decimal("5"), risk_config).approved


def test_blocks_size_above_configured(risk_config):
    decision = check_position_size(Decimal("10.01"), risk_config)

    assert not decision.approved
    assert RejectionCode.POSITION_SIZE_EXCEEDED in decision.codes


@pytest.mark.parametrize("size", ["0", "-5"])
def test_blocks_non_positive_size(risk_config, size):
    decision = check_position_size(Decimal(size), risk_config)

    assert not decision.approved
    assert RejectionCode.POSITION_SIZE_INVALID in decision.codes


def test_blocks_runtime_size_above_ceiling_even_when_config_permits_it():
    """A config with an acknowledged override still caps at its own value."""
    config = RiskConfig(position_size_usd=Decimal("50"), position_size_override_ack=True)

    assert check_position_size(Decimal("50"), config).approved
    assert not check_position_size(Decimal("50.01"), config).approved
