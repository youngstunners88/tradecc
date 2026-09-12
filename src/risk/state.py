"""Persistent daily risk state.

The circuit breaker has to survive a restart. If it did not, killing and
relaunching the process would be an accidental way to clear a halt and keep
trading into a losing day — the exact failure the breaker exists to prevent.

State is keyed by UTC trading day. Loading state from a previous day yields
a fresh, un-halted state for today; yesterday's halt does not carry over,
and today's cannot be erased by a restart.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from core.types import finite_decimal


def current_trading_day(now: datetime | None = None) -> date:
    """Trading days run on UTC boundaries."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return moment.astimezone(timezone.utc).date()


@dataclass(frozen=True)
class DailyRiskState:
    trading_day: date
    realized_pnl_usd: Decimal = Decimal("0")
    trade_count: int = 0
    halted: bool = False
    halt_reason: str | None = None

    def with_pnl(self, delta_usd: Decimal) -> DailyRiskState:
        return replace(
            self,
            realized_pnl_usd=self.realized_pnl_usd + delta_usd,
            trade_count=self.trade_count + 1,
        )

    def halt(self, reason: str) -> DailyRiskState:
        # A halt latches: the first reason is the one that stands, so the
        # audit trail shows what actually stopped trading.
        if self.halted:
            return self
        return replace(self, halted=True, halt_reason=reason)

    def to_dict(self) -> dict[str, object]:
        return {
            "trading_day": self.trading_day.isoformat(),
            "realized_pnl_usd": str(self.realized_pnl_usd),
            "trade_count": self.trade_count,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }

    @staticmethod
    def from_dict(raw: dict[str, object]) -> DailyRiskState:
        return DailyRiskState(
            trading_day=date.fromisoformat(str(raw["trading_day"])),
            # Finite only. A hand-edited or mis-serialised "Infinity" here
            # absorbs every subsequent loss, so the breaker never trips; "NaN"
            # raises out of the breach comparison. Either silently disables the
            # control this module exists to make durable.
            realized_pnl_usd=_finite_or_raise(raw.get("realized_pnl_usd", "0")),
            trade_count=int(raw.get("trade_count", 0) or 0),
            halted=bool(raw.get("halted", False)),
            halt_reason=raw.get("halt_reason") or None,  # type: ignore[arg-type]
        )


def _finite_or_raise(value: object) -> Decimal:
    """Reject non-finite P&L. Raises so `RiskStateStore.load` treats the file
    as corrupt and starts the day clean rather than trusting the value."""
    parsed = finite_decimal(value)
    if parsed is None:
        raise ValueError(f"realized_pnl_usd is not a finite decimal: {value!r}")
    return parsed


class RiskStateStorage(Protocol):
    """Where daily risk state lives.

    Two implementations: on disk for real runs, where surviving a restart
    is the whole point, and in memory for backtests, where persistence
    would be a bug — a halt from one backtest leaking into the next makes
    results depend on run order.
    """

    def load(self, now: datetime | None = None) -> DailyRiskState: ...

    def save(self, state: DailyRiskState) -> None: ...


class InMemoryRiskStateStore:
    """Isolated per-instance state, for backtests and tests."""

    def __init__(self) -> None:
        self._state: DailyRiskState | None = None

    def load(self, now: datetime | None = None) -> DailyRiskState:
        today = current_trading_day(now)
        if self._state is None or self._state.trading_day != today:
            return DailyRiskState(trading_day=today)
        return self._state

    def save(self, state: DailyRiskState) -> None:
        self._state = state


class RiskStateStore:
    """JSON-file-backed store for the current trading day's risk state."""

    def __init__(self, state_dir: Path | str) -> None:
        self._path = Path(state_dir) / "daily-risk-state.json"

    @property
    def path(self) -> Path:
        return self._path

    def load(self, now: datetime | None = None) -> DailyRiskState:
        today = current_trading_day(now)
        if not self._path.is_file():
            return DailyRiskState(trading_day=today)
        try:
            stored = DailyRiskState.from_dict(json.loads(self._path.read_text()))
        except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError):
            # Corrupt state is not a reason to trade unrestricted, but it is
            # also not evidence of a loss. Start the day clean and let the
            # breaker re-accumulate from real fills.
            return DailyRiskState(trading_day=today)
        if stored.trading_day != today:
            return DailyRiskState(trading_day=today)
        return stored

    def save(self, state: DailyRiskState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-replace so a crash mid-write cannot truncate the file
        # and silently discard a halt.
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=2))
        os.replace(tmp, self._path)
