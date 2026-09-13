"""Domain types shared across strategy, risk, and execution.

Money is always `Decimal`, never `float`. Binary floating point cannot
represent decimal fractions exactly, and accumulating rounding error into
P&L is how a circuit breaker ends up comparing against a number that is
quietly wrong.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum


class Mode(str, Enum):
    """Run mode. `LIVE` is gated — see `core.gate`."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"

    @property
    def sends_real_transactions(self) -> bool:
        return self is Mode.LIVE


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class Candle:
    """One OHLCV bar. `timestamp` is the bar's open time, always UTC."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Candle.timestamp must be timezone-aware (UTC)")


@dataclass(frozen=True)
class Signal:
    """A strategy's opinion. Carries no sizing — that is risk's job."""

    type: SignalType
    token_mint: str
    price: Decimal
    timestamp: datetime
    strategy: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Quote:
    """A priced route from the execution layer (real or simulated).

    `expected_price` is what the route implies; `worst_case_price` is what
    the route guarantees at the quoted slippage tolerance. Risk compares
    the two — a quote that only reports its optimistic leg is unusable.
    """

    token_mint: str
    side: Side
    amount_usd: Decimal
    expected_price: Decimal
    worst_case_price: Decimal
    fee_usd: Decimal
    source: str

    @property
    def slippage_pct(self) -> Decimal:
        """Effective slippage between expected and worst-case fill, in percent."""
        if self.expected_price <= 0:
            raise ValueError("Quote.expected_price must be positive")
        delta = abs(self.worst_case_price - self.expected_price)
        return (delta / self.expected_price) * Decimal(100)


@dataclass(frozen=True)
class TradeIntent:
    """A proposed trade, before risk approval.

    Nothing downstream of risk may construct one of these and act on it
    without passing it through `RiskEngine.approve` first.
    """

    signal: Signal
    quote: Quote
    size_usd: Decimal
    mode: Mode


@dataclass(frozen=True)
class Position:
    token_mint: str
    entry_price: Decimal
    size_usd: Decimal
    opened_at: datetime

    def unrealized_pnl_usd(self, current_price: Decimal) -> Decimal:
        if self.entry_price <= 0:
            raise ValueError("Position.entry_price must be positive")
        return self.size_usd * (current_price - self.entry_price) / self.entry_price

    def unrealized_pnl_pct(self, current_price: Decimal) -> Decimal:
        if self.entry_price <= 0:
            raise ValueError("Position.entry_price must be positive")
        return ((current_price - self.entry_price) / self.entry_price) * Decimal(100)


@dataclass(frozen=True)
class Fill:
    """A completed trade — simulated in backtest/paper, real in live."""

    token_mint: str
    side: Side
    price: Decimal
    size_usd: Decimal
    fee_usd: Decimal
    timestamp: datetime
    simulated: bool
    tx_signature: str | None = None


class RejectionCode(str, Enum):
    """Why risk vetoed a trade. Stable strings — these get logged and asserted on."""

    SLIPPAGE_EXCEEDED = "slippage_exceeded"
    POSITION_SIZE_EXCEEDED = "position_size_exceeded"
    POSITION_SIZE_INVALID = "position_size_invalid"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    LIVE_GATE_NOT_MET = "live_gate_not_met"


@dataclass(frozen=True)
class RiskDecision:
    """Risk's verdict. `approved` is the only thing execution may act on."""

    approved: bool
    rejections: tuple[tuple[RejectionCode, str], ...] = ()

    @staticmethod
    def approve() -> RiskDecision:
        return RiskDecision(approved=True)

    @staticmethod
    def reject(code: RejectionCode, detail: str) -> RiskDecision:
        return RiskDecision(approved=False, rejections=((code, detail),))

    def merged_with(self, other: RiskDecision) -> RiskDecision:
        """Combine verdicts. Any rejection wins — checks never cancel out."""
        rejections = self.rejections + other.rejections
        return RiskDecision(approved=not rejections, rejections=rejections)

    @property
    def codes(self) -> tuple[RejectionCode, ...]:
        return tuple(code for code, _ in self.rejections)

    def describe(self) -> str:
        if self.approved:
            return "approved"
        return "; ".join(f"{code.value}: {detail}" for code, detail in self.rejections)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def finite_decimal(value: object) -> Decimal | None:
    """Parse a money-ish value to a **finite** Decimal, or None.

    `Decimal(str(x))` happily accepts `NaN` and `Infinity`, and both arrive
    through ordinary paths: `json.loads` parses the bare literals `NaN`,
    `Infinity` and `-Infinity` by default, and any float that overflows
    stringifies to `inf`. Neither value is a quantity of money, and both break
    the comparisons that safety controls are built from:

    - `Decimal("NaN") >= limit` raises `InvalidOperation`, turning a risk check
      into an uncaught crash.
    - `Decimal("Infinity")` absorbs every loss, so a circuit breaker comparing
      against it can never trip — a $1000 loss against a $5 limit does not halt.

    Booleans are rejected too: `True` is an `int` in Python, and a JSON `true`
    silently becoming `Decimal(1)` is never what the caller meant.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


@dataclass(frozen=True)
class SimulationOutcome:
    """The result of simulating one transaction against the live cluster.

    `transaction_digest` identifies the exact bytes simulated. It is the whole
    point of this type: without it, "a simulation succeeded" is a claim about
    some transaction, not about the one being sent.
    """

    transaction_digest: str
    succeeded: bool
    simulated_at: datetime
    error: str | None = None
    logs: tuple[str, ...] = ()


def digest_of(transaction_bytes: bytes) -> str:
    """SHA-256 over a serialised transaction.

    Lives here because both the execution layer (which simulates) and the live
    layer (which authorises) must agree on what identifies a transaction. Two
    implementations of "which transaction is this" would eventually disagree,
    and the disagreement would authorise a send of bytes nobody simulated.
    """
    return hashlib.sha256(transaction_bytes).hexdigest()
