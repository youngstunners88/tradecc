"""Momentum strategy: EMA crossover with an RSI filter.

The rules:

- **BUY** when the fast EMA crosses *above* the slow EMA, and RSI is not
  already overbought.
- **SELL** when the fast EMA crosses *below* the slow EMA, or RSI is
  overbought.
- **HOLD** otherwise.

The RSI filter on entry is the part that earns its keep. A bare EMA
crossover buys strength wherever it appears, including at the exhausted
top of a move — which at $5–$10 sizes, where fixed costs already take a
percent or more, is a reliable way to lose money slowly.

Signals are emitted only on a *crossover*, never on a persistent state.
"Fast is above slow" is true for as long as a trend runs; acting on that
every bar would re-enter continuously and pay the cost stack each time.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

from core.types import Candle, Signal, SignalType
from pydantic import BaseModel, ConfigDict, model_validator
from strategy.indicators import ema, rsi

NAME = "momentum"


class MomentumParams(BaseModel):
    """Strategy parameters, validated by the strategy itself.

    Strict: an unknown key here is a typo'd parameter, and silently
    ignoring it would mean running a strategy the operator did not
    configure.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fast_ema: int = 12
    slow_ema: int = 26
    rsi_period: int = 14
    rsi_overbought: Decimal = Decimal("70")
    rsi_oversold: Decimal = Decimal("30")

    @model_validator(mode="after")
    def _check(self) -> MomentumParams:
        if self.fast_ema < 1 or self.slow_ema < 1 or self.rsi_period < 1:
            raise ValueError("EMA and RSI periods must be at least 1")
        if self.fast_ema >= self.slow_ema:
            raise ValueError(
                f"fast_ema ({self.fast_ema}) must be shorter than slow_ema "
                f"({self.slow_ema}); otherwise the crossover has no meaning"
            )
        if not (Decimal(0) < self.rsi_oversold < self.rsi_overbought < Decimal(100)):
            raise ValueError(
                "require 0 < rsi_oversold < rsi_overbought < 100 "
                f"(got {self.rsi_oversold} and {self.rsi_overbought})"
            )
        return self


class MomentumStrategy:
    def __init__(self, params: MomentumParams | None = None) -> None:
        self._params = params or MomentumParams()

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> MomentumStrategy:
        return cls(MomentumParams(**params))

    @property
    def name(self) -> str:
        return NAME

    @property
    def params(self) -> MomentumParams:
        return self._params

    @property
    def minimum_candles(self) -> int:
        """Enough history for both indicators *plus* one prior bar.

        The extra bar is not padding: detecting a crossover requires
        knowing which side the fast EMA was on previously.
        """
        return max(self._params.slow_ema, self._params.rsi_period + 1) + 1

    def generate(self, token_mint: str, candles: Sequence[Candle]) -> Signal:
        if not candles:
            raise ValueError("cannot generate a signal from an empty candle series")

        latest = candles[-1]
        if len(candles) < self.minimum_candles:
            return self._signal(
                SignalType.HOLD,
                token_mint,
                latest,
                reason="insufficient_history",
                detail=f"{len(candles)} candles, need {self.minimum_candles}",
            )

        closes = [candle.close for candle in candles]
        fast = ema(closes, self._params.fast_ema)
        slow = ema(closes, self._params.slow_ema)
        strength = rsi(closes, self._params.rsi_period)

        fast_now, fast_prev = fast[-1], fast[-2]
        slow_now, slow_prev = slow[-1], slow[-2]
        rsi_now = strength[-1]

        if (
            fast_now is None
            or fast_prev is None
            or slow_now is None
            or slow_prev is None
            or rsi_now is None
        ):
            return self._signal(
                SignalType.HOLD,
                token_mint,
                latest,
                reason="indicator_warmup",
                detail="indicators not yet defined for the previous bar",
            )

        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now
        overbought = rsi_now >= self._params.rsi_overbought

        metadata = {
            "fast_ema": str(fast_now),
            "slow_ema": str(slow_now),
            "rsi": str(rsi_now),
        }

        if crossed_down:
            return self._signal(
                SignalType.SELL, token_mint, latest, "ema_cross_down", metadata=metadata
            )
        if overbought:
            return self._signal(
                SignalType.SELL, token_mint, latest, "rsi_overbought", metadata=metadata
            )
        if crossed_up:
            return self._signal(
                SignalType.BUY, token_mint, latest, "ema_cross_up", metadata=metadata
            )
        return self._signal(
            SignalType.HOLD, token_mint, latest, "no_crossover", metadata=metadata
        )

    def _signal(
        self,
        signal_type: SignalType,
        token_mint: str,
        candle: Candle,
        reason: str,
        detail: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Signal:
        payload = {"reason": reason, **(metadata or {})}
        if detail:
            payload["detail"] = detail
        return Signal(
            type=signal_type,
            token_mint=token_mint,
            price=candle.close,
            # The candle's own timestamp, never the wall clock: a signal
            # must be reproducible when the series is replayed.
            timestamp=candle.timestamp,
            strategy=NAME,
            metadata=payload,
        )
