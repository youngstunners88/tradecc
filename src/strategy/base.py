"""The strategy boundary.

A strategy is a **pure function of closed candles**: same candles in, same
signal out, no I/O, no clock, no randomness. That purity is what makes a
backtest meaningful — a strategy that consulted the wall clock or the
network could not be replayed, and the validation gate would be measuring
something other than what runs live.

Strategies are also stateless about positions. They emit BUY / SELL / HOLD
from the price series; whether we currently hold the token, and what to do
about it, belongs to the caller and to `risk/`. That separation is what
lets v0.2 copy-trading drop in against this same protocol without touching
execution or risk.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from core.types import Candle, Signal


@runtime_checkable
class Strategy(Protocol):
    """Turns a price series into a trading signal."""

    @property
    def name(self) -> str: ...

    @property
    def minimum_candles(self) -> int:
        """Candles needed before a signal can be produced at all."""
        ...

    def generate(self, token_mint: str, candles: Sequence[Candle]) -> Signal: ...
