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
    """Anything that can price a prospective swap."""

    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        slippage_bps: int,
        amount_usd: Decimal,
        side: Side = Side.BUY,
    ) -> Quote: ...
