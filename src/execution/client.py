"""The execution boundary.

`execution/` is the only package that talks to the network or touches the
wallet key. Everything above it depends on this protocol, not on Jupiter
or Helius specifically, which is what lets a mock stand in for the real
thing in tests and what will let v0.2 copy-trading reuse the same layer.

Stage 2 is deliberately quote-only: there is no method here that builds,
signs, or sends a transaction. Live execution arrives in Stage 6, behind
the validation gate.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from core.types import Quote, Side


@runtime_checkable
class QuoteSource(Protocol):
    """Anything that can price a prospective swap.

    Implementations must honour one price convention: `expected_price` and
    `worst_case_price` are **quote asset per token on both sides**, in human
    units rather than atomic ones, with `worst_case_price` adverse for the
    side (higher on a BUY, lower on a SELL). A source that returns the
    reciprocal on SELLs silently inverts every exit price.

    `input_decimals` and `output_decimals` have no defaults on purpose: they
    are what convert an atomic ratio into that price, and a default would be
    a silent wrong answer on every pair that did not match it.
    """

    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        slippage_bps: int,
        amount_usd: Decimal,
        input_decimals: int,
        output_decimals: int,
        *,
        side: Side = Side.BUY,
    ) -> Quote: ...
