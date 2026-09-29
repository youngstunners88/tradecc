"""
Position reconstruction for copy-wallet research.

Given DEX trade records, this builds a per-wallet, per-mint position book
from buy/sell prints. Money is Decimal everywhere.

The maths is intentionally simple: a BUY adds to the position, a SELL
reduces it. We do not model fees, rebates, or complex DeFi moves; this is
a first-pass position book for ranking purposes. The note in the work
order says "balance-delta, or side + amount from Bitquery's DEXTrade
fields" — we follow that literally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol


class TradeSource(Protocol):
    """Extract a trade from a provider-specific record."""

    def extract_trades(
        self, address: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """Return list of raw trade dicts."""


@dataclass(frozen=True)
class TradeSide:
    SIDE_BUY = "BUY"
    SIDE_SELL = "SELL"
    SIDE_UNKNOWN = "UNKNOWN"


@dataclass
class Position:
    wallet: str
    mint: str
    units: Decimal = Decimal("0")
    net_quote_in: Decimal = Decimal("0")
    net_quote_out: Decimal = Decimal("0")
    n_buys: int = 0
    n_sells: int = 0
    last_activity: datetime | None = None

    @property
    def net_pnl_quote(self) -> Decimal:
        return self.net_quote_out - self.net_quote_in


@dataclass
class PositionBook:
    positions: dict[tuple[str, str], Position] = field(default_factory=dict)

    def add_trade(
        self,
        wallet: str,
        mint: str,
        side: str,
        amount: Decimal,
        quote_amount: Decimal | None,
        timestamp: datetime,
    ) -> None:
        key = (wallet, mint)
        pos = self.positions.get(key)
        if pos is None:
            pos = Position(wallet=wallet, mint=mint, units=Decimal("0"))
            self.positions[key] = pos

        if side.upper() == TradeSide.SIDE_BUY:
            pos.units += amount
            if quote_amount is not None:
                pos.net_quote_in += quote_amount
                pos.net_quote_out += Decimal("0")  # ensure field present
            pos.n_buys += 1
        elif side.upper() == TradeSide.SIDE_SELL:
            pos.units -= amount
            if quote_amount is not None:
                pos.net_quote_out += quote_amount
                pos.net_quote_in += Decimal("0")  # ensure field present
            pos.n_sells += 1
        else:
            # Unknown side: skip for position size but still record activity.
            pos.last_activity = timestamp

        if pos.last_ts is None or timestamp > pos.last_ts:
            pos.last_ts = timestamp


def build_position_book(
    trades: list[dict[str, Any]],
    field_map: dict[str, str] | None = None,
) -> PositionBook:
    """Build a position book from raw trade records.

    field_map may override which keys contain wallet, mint, side, amount,
    and quote amount. By default we use the shapes from
    bitquery_client.py's assumed DEX trade schema. All money fields are
    converted to Decimal.
    """
    book = PositionBook()

    map = field_map or {
        "wallet": "account.trader",
        "mint": "baseToken.mint",
        "side": "side",
        "amount": "baseAmount",
        "quote_amount": "quoteAmount",
        "timestamp": "block.timestamp",
    }

    for trade in trades:
        def _get(trade: dict[str, Any], path: str) -> Any:
            current: Any = trade
            for part in path.split("."):
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
            return current

        wallet = _get(trade, map["wallet"])
        mint = _get(trade, map["mint"])
        side = _get(trade, map["side"])
        amount = _get(trade, map["amount"])
        quote_amount = _get(trade, map["quote_amount"])
        ts_raw = _get(trade, map["timestamp"])

        if wallet is None or mint is None or side is None:
            continue

        # Parse the timestamp.
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = datetime.min.replace(tzinfo=__import__("datetime").timezone.utc)

        # Money conversion: must be Decimal, not float.
        try:
            amount_dec = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            amount_dec = Decimal("0")

        if quote_amount is not None:
            try:
                quote_dec = Decimal(str(quote_amount))
            except (InvalidOperation, TypeError, ValueError):
                quote_dec = None
        else:
            quote_dec = None

        book.add_trade(wallet, mint, side, amount_dec, quote_dec, ts)

    return book
