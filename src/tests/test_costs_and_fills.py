"""Cost modelling and fill simulation.

At $5–$10 sizes these numbers decide whether a strategy is real, so the
tests assert on exact figures rather than "roughly right".
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.config import CostsConfig
from core.types import Side
from execution.costs import CostModel, TradeCosts
from execution.fills import FillSimulator
from execution.mock import MockQuoteSource

TOKEN = "So11111111111111111111111111111111111111112"


@pytest.fixture
def costs_config() -> CostsConfig:
    return CostsConfig(
        base_fee_lamports=5000,
        compute_unit_limit=200_000,
        priority_fee_microlamports_per_cu=200_000,
        jito_tip_lamports=17_392,
        ata_rent_lamports=2_039_280,
        platform_fee_bps=0,
        sol_price_usd=Decimal("200"),
    )


@pytest.fixture
def model(costs_config) -> CostModel:
    return CostModel(costs_config)


def test_network_fee_converts_lamports_to_usd(model):
    costs = model.estimate(Decimal("10"))

    # 5000 lamports = 5e-6 SOL; at $200 that is $0.001.
    assert costs.network_fee_usd == Decimal("0.001")


def test_priority_fee_is_per_compute_unit_not_a_flat_total(model):
    """The bug this replaced: a flat reading understated the fee ~200,000x.

    200_000 CU x 200_000 microlamports/CU = 4e10 microlamports = 40,000
    lamports = 4e-5 SOL, which is $0.008 at $200/SOL. Read as a flat
    total the same config produced $0.00000004.
    """
    costs = model.estimate(Decimal("10"))

    assert model.priority_fee_lamports() == Decimal("40000")
    assert costs.priority_fee_usd == Decimal("0.008")


def test_jito_tip_is_modelled_rather_than_assumed_free(model):
    # 17_392 lamports = 1.7392e-5 SOL; at $200 that is $0.0034784.
    costs = model.estimate(Decimal("10"))

    assert costs.jito_tip_usd == Decimal("0.0034784")
    assert costs.jito_tip_usd > 0


def test_sol_price_override_reprices_every_sol_denominated_cost(model):
    """A stale SOL price misprices all of them at once, in one direction."""
    at_200 = model.estimate(Decimal("10"), creates_token_account=True)
    at_100 = model.estimate(
        Decimal("10"), creates_token_account=True, sol_price_usd=Decimal("100")
    )

    assert at_100.network_fee_usd == at_200.network_fee_usd / 2
    assert at_100.priority_fee_usd == at_200.priority_fee_usd / 2
    assert at_100.jito_tip_usd == at_200.jito_tip_usd / 2
    assert at_100.account_rent_usd == at_200.account_rent_usd / 2
    assert at_100.sol_price_usd == Decimal("100")


def test_recurring_cost_excludes_the_refundable_rent_deposit(model):
    """Rent is a one-time refundable deposit, not a per-trade fee."""
    costs = model.estimate(Decimal("10"), creates_token_account=True)

    assert costs.account_rent_usd > 0
    assert costs.recurring_usd == costs.total_usd - costs.account_rent_usd
    assert costs.recurring_usd < costs.total_usd


def test_no_account_rent_when_the_account_exists(model):
    assert model.estimate(Decimal("10")).account_rent_usd == Decimal("0")


def test_account_rent_dominates_at_small_sizes(model):
    """The first trade in a new mint is far more expensive than the rest.

    The margin narrowed sharply once priority fees were modelled per
    compute unit and Jito tips stopped being counted as zero: rent used
    to be >400x a recurring transaction and is now ~33x. Rent is still
    the largest single line, but it is one-time and refundable, whereas
    the recurring costs are neither.
    """
    fresh = model.estimate(Decimal("10"), creates_token_account=True)
    existing = model.estimate(Decimal("10"), creates_token_account=False)

    # ~0.00204 SOL at $200 = ~$0.41.
    assert fresh.account_rent_usd == Decimal("0.40785600")
    assert fresh.total_usd > existing.total_usd * 30
    assert fresh.total_usd < existing.total_usd * 40


def test_cost_as_percentage_of_a_small_position(model):
    costs = model.estimate(Decimal("5"), creates_token_account=True)

    # Over 8% of a $5 position gone before the price moves at all.
    assert costs.as_pct_of(Decimal("5")) > Decimal("8")


def test_platform_fee_scales_with_size(costs_config):
    model = CostModel(costs_config.model_copy(update={"platform_fee_bps": 20}))

    assert model.estimate(Decimal("10")).platform_fee_usd == Decimal("0.02")


def test_total_sums_every_component():
    costs = TradeCosts(
        network_fee_usd=Decimal("0.001"),
        priority_fee_usd=Decimal("0.002"),
        jito_tip_usd=Decimal("0.004"),
        account_rent_usd=Decimal("0.4"),
        platform_fee_usd=Decimal("0.02"),
        sol_price_usd=Decimal("100"),
    )

    assert costs.total_usd == Decimal("0.427")
    assert costs.recurring_usd == Decimal("0.027")


@pytest.mark.parametrize("size", ["0", "-5"])
def test_rejects_non_positive_size(model, size):
    with pytest.raises(ValueError):
        model.estimate(Decimal(size))


def test_fill_uses_the_worst_case_price_not_the_expected_one(model):
    """Optimistic paper fills produce a gate that passes losing systems."""
    quote = MockQuoteSource(
        expected_price=Decimal("100"), slippage_pct=Decimal("1")
    ).get_quote("usdc", TOKEN, 1_000, 100, Decimal("10"))

    fill = FillSimulator(model).simulate(quote, Decimal("10"))

    assert fill.price == quote.worst_case_price
    assert fill.price == Decimal("101")


def test_fill_is_marked_simulated_and_has_no_signature(model):
    quote = MockQuoteSource().get_quote("usdc", TOKEN, 1_000, 50, Decimal("10"))

    fill = FillSimulator(model).simulate(quote, Decimal("10"))

    assert fill.simulated is True
    assert fill.tx_signature is None


def test_fill_carries_the_modelled_costs(model):
    quote = MockQuoteSource().get_quote("usdc", TOKEN, 1_000, 50, Decimal("10"))

    fill = FillSimulator(model).simulate(quote, Decimal("10"), creates_token_account=True)

    assert fill.fee_usd == model.estimate(Decimal("10"), True).total_usd


def test_fill_preserves_side_and_mint(model):
    quote = MockQuoteSource().get_quote("usdc", TOKEN, 1_000, 50, Decimal("10"), Side.SELL)

    fill = FillSimulator(model).simulate(quote, Decimal("10"))

    assert fill.token_mint == TOKEN
    assert fill.side is Side.SELL


def test_mock_quote_source_records_calls():
    source = MockQuoteSource()

    source.get_quote("usdc", TOKEN, 5_000, 50, Decimal("7"))

    assert source.calls[0].amount_atomic == 5_000
    assert source.calls[0].amount_usd == Decimal("7")


def test_mock_quote_source_produces_the_requested_slippage():
    source = MockQuoteSource(expected_price=Decimal("50"), slippage_pct=Decimal("0.3"))

    quote = source.get_quote("usdc", TOKEN, 1_000, 30, Decimal("10"))

    assert quote.slippage_pct == pytest.approx(Decimal("0.3"))
