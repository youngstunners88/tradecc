"""Copy-wallet strategy implementation.

The fill log is injected at construction time rather than fetched inside
generate() because a strategy must be a pure function of closed candles: same
fills and same candles in, same signal out. A network or wall-clock read in
generate() would make the strategy non-replayable and would break the backtest
versus live equivalence this repository relies on.

The look-ahead boundary is enforced by the comparison in generate():
fill.timestamp + lag_seconds <= candles[-1].timestamp. The latest closed
candle's timestamp is the only notion of "now" available to a strategy, and no
fill later than that boundary is eligible. Lag is therefore applied in the
backtest and in paper identically.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional, Sequence

from core.types import Candle, Signal, SignalType

NAME = "copy"


@dataclass(frozen=True)
class SourceFill:
    timestamp: datetime
    wallet: str
    token_mint: str
    side: str
    amount: Decimal

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("SourceFill.timestamp must be timezone-aware")
        if self.side not in ("buy", "sell"):
            raise ValueError("SourceFill.side must be 'buy' or 'sell'")


class CopyStrategy:
    """Replay-safe copy-wallet strategy.

    Fills are frozen at construction time. If `allowlist` is supplied, the
    constructor filters the fill log to those wallets; if it is omitted, the
    fills are assumed to already be filtered. The stored tuple is always
    sorted by timestamp.
    """

    def __init__(
        self,
        fills: Sequence[SourceFill],
        lag_seconds: int = 60,
        allowlist: Optional[Sequence[str]] = None,
    ) -> None:
        if isinstance(lag_seconds, bool) or not isinstance(lag_seconds, int):
            raise ValueError("lag_seconds must be an integer")
        if lag_seconds < 60:
            raise ValueError(
                "lag_seconds must be at least 60: with 1m bar resolution "
                "a sub-minute lag would be fiction"
            )

        if allowlist is not None:
            allowed = set(allowlist)
            fills = [fill for fill in fills if fill.wallet in allowed]

        self._fills = tuple(sorted(fills, key=lambda fill: fill.timestamp))
        self._lag_seconds = lag_seconds
        self._allowlist = tuple(allowlist) if allowlist is not None else None
        # Set only by `from_params`. See `generate` for why it exists.
        self._awaiting_fills = False

    def with_fills(self, fills: Sequence[SourceFill]) -> "CopyStrategy":
        """Return a new strategy carrying this fill log.

        A new instance rather than a mutation: the fill log is frozen at
        construction precisely so a run cannot change what it is replaying
        halfway through.
        """
        return CopyStrategy(
            fills=fills, lag_seconds=self._lag_seconds, allowlist=self._allowlist
        )

    @property
    def name(self) -> str:
        return NAME

    @property
    def minimum_candles(self) -> int:
        return 1

    def generate(self, token_mint: str, candles: Sequence[Candle]) -> Signal:
        if not candles:
            raise ValueError("generate() requires at least one candle")

        # A strategy built from config has no fill log — YAML cannot carry
        # one. Left alone it would return HOLD on every bar, forever, and a
        # paper run would look exactly like a working strategy in a quiet
        # market. That silence could cost a whole test window before anyone
        # noticed, so it fails loudly on the first bar instead.
        if self._awaiting_fills:
            raise ValueError(
                "CopyStrategy was built from config and has no fill log. "
                "Attach one with `strategy.with_fills(...)` before running. "
                "Returning HOLD forever would be indistinguishable from a "
                "working strategy that found no signals."
            )

        now = candles[-1].timestamp
        price = candles[-1].close
        lag = timedelta(seconds=self._lag_seconds)
        eligible: Optional[SourceFill] = None

        for fill in self._fills:
            # An early exit, NOT a correctness control. Verified by mutation:
            # deleting these two lines changes no observable behaviour and
            # fails no test, because any fill with `timestamp > now` also
            # fails `timestamp + lag <= now` below for any lag >= 0.
            #
            # Kept because it stops the scan sooner on a long fill log, and
            # documented because a reader could otherwise mistake it for the
            # look-ahead guard and reason about ordering around it. The
            # look-ahead guard is the comparison further down; that one is
            # load-bearing and its removal fails three tests.
            if fill.timestamp > now:
                break

            if fill.token_mint != token_mint:
                continue

            if fill.timestamp + lag <= now:
                eligible = fill
            else:
                break

        if eligible is None:
            return Signal(
                type=SignalType.HOLD,
                token_mint=token_mint,
                price=price,
                timestamp=now,
                strategy=NAME,
                metadata={},
            )

        signal_type = SignalType.BUY if eligible.side == "buy" else SignalType.SELL
        return Signal(
            type=signal_type,
            token_mint=token_mint,
            price=price,
            timestamp=now,
            strategy=NAME,
            metadata={
                "source_wallet": eligible.wallet,
                "source_fill_ts": eligible.timestamp.isoformat(),
            },
        )

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> "CopyStrategy":
        if not isinstance(params, dict):
            raise ValueError("params must be a dict")

        unknown = set(params) - {"lag_seconds", "allowlist"}
        if unknown:
            raise ValueError(
                "unknown parameter(s): " + ", ".join(sorted(unknown))
            )

        lag_seconds = params.get("lag_seconds", 60)
        if isinstance(lag_seconds, bool) or not isinstance(lag_seconds, int):
            raise ValueError("lag_seconds must be an integer")
        if lag_seconds < 60:
            raise ValueError(
                "lag_seconds must be at least 60: with 1m bar resolution "
                "a sub-minute lag would be fiction"
            )

        allowlist_raw = params.get("allowlist", ())
        if isinstance(allowlist_raw, (str, bytes)):
            raise ValueError(
                "allowlist must be a sequence of wallet address strings"
            )

        try:
            allowlist = tuple(allowlist_raw)
        except TypeError:
            raise ValueError(
                "allowlist must be a sequence of wallet address strings"
            ) from None

        if any(not isinstance(address, str) for address in allowlist):
            raise ValueError("allowlist entries must be wallet address strings")

        strategy = cls(fills=(), lag_seconds=lag_seconds, allowlist=allowlist)
        strategy._awaiting_fills = True
        return strategy
