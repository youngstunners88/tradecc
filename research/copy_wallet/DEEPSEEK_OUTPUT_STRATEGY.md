> **Provenance:** DeepSeek-assisted (`deepseek/deepseek-v4-pro-0813` via OpenRouter, 2026-09-16).
> Drafted by the model. **Not yet reviewed** — review and independently
> re-derive every numeric claim before adopting this, and replace this
> line with the reviewed form from
> `.claude/skills/openrouter-deepseek/SKILL.md` once you have.
>
> Sources supplied to the model: `research/copy_wallet/INTERFACE_BRIEF.md`.

```python
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

from src.core.types import Candle, Signal, SignalType

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

    @property
    def name(self) -> str:
        return NAME

    @property
    def minimum_candles(self) -> int:
        return 1

    def generate(self, token_mint: str, candles: Sequence[Candle]) -> Signal:
        if not candles:
            raise ValueError("generate() requires at least one candle")

        now = candles[-1].timestamp
        price = candles[-1].close
        lag = timedelta(seconds=self._lag_seconds)
        eligible: Optional[SourceFill] = None

        for fill in self._fills:
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

        return cls(fills=(), lag_seconds=lag_seconds, allowlist=allowlist)
```

## Notes

- The main ambiguity is that the interface brief snippet says `__init__` receives fills already filtered to the allowlist, while requirement 3 says the constructor filters to the allowlist. This implementation supports both: if `allowlist` is provided, filtering happens inside `__init__`; if omitted, fills are treated as already filtered. The final tuple is always sorted by timestamp.
- `from_params` intentionally constructs an empty-fill strategy. Fill logs are injected through `__init__` by research/backtest code, not through the param registry, because strategy code must not perform I/O.
- Signal metadata contains only the source wallet and source fill timestamp as strings. No size is carried.
