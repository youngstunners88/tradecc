from __future__ import annotations

from decimal import Decimal

import pytest

from core.types import RejectionCode, Side
from risk.slippage import check_slippage
from tests.conftest import make_quote


def test_approves_slippage_within_cap():
    quote = make_quote(expected="100", worst_case="100.3")  # 0.3%

    assert check_slippage(quote, Decimal("0.5")).approved


def test_blocks_slippage_over_cap():
    quote = make_quote(expected="100", worst_case="101.5")  # 1.5%

    decision = check_slippage(quote, Decimal("0.5"))

    assert not decision.approved
    assert RejectionCode.SLIPPAGE_EXCEEDED in decision.codes


def test_slippage_exactly_at_cap_is_allowed():
    quote = make_quote(expected="100", worst_case="100.5")  # exactly 0.5%

    assert check_slippage(quote, Decimal("0.5")).approved


def test_adverse_slippage_is_measured_in_both_directions():
    """A sell whose worst case is below expected is still slippage."""
    quote = make_quote(expected="100", worst_case="98", side=Side.SELL)  # 2%

    assert not check_slippage(quote, Decimal("0.5")).approved


def test_uses_worst_case_not_expected_price():
    # Expected price alone looks perfect; only the worst-case leg reveals the risk.
    quote = make_quote(expected="100", worst_case="105")

    assert not check_slippage(quote, Decimal("1")).approved


def test_rejects_non_positive_cap():
    with pytest.raises(ValueError):
        check_slippage(make_quote(), Decimal("0"))


def test_quote_with_non_positive_expected_price_raises():
    quote = make_quote(expected="0", worst_case="1")

    with pytest.raises(ValueError):
        check_slippage(quote, Decimal("0.5"))
