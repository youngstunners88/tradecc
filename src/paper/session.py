"""Persistent paper-trading session state.

The validation gate needs 30 continuous days. That makes persistence a
correctness requirement rather than a convenience: a VPS reboot on day 19
must not silently restart the clock or lose the trade journal that the
gate is evidence from.

So the session records everything the gate reads — when it started, every
closed trade, the open position — and reloads it on start. `elapsed_days`
is measured from the *first* start, never from the last restart.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from core.performance import (
    ClosedTrade,
    equity_curve_from,
    expectancy,
    gross_pnl,
    max_drawdown_pct,
    net_pnl,
    total_fees,
    win_rate_pct,
)
from core.types import Position


@dataclass
class PaperSessionState:
    token_mint: str
    strategy_name: str
    started_at: datetime
    initial_capital_usd: Decimal
    trades: list[ClosedTrade] = field(default_factory=list)
    open_position: Position | None = None
    open_entry_fees_usd: Decimal = Decimal(0)
    funded_mints: set[str] = field(default_factory=set)
    ticks: int = 0
    last_tick_at: datetime | None = None

    # --- metrics, computed by the same code as the backtest ---

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def gross_pnl_usd(self) -> Decimal:
        return gross_pnl(self.trades)

    @property
    def total_fees_usd(self) -> Decimal:
        return total_fees(self.trades)

    @property
    def net_pnl_usd(self) -> Decimal:
        return net_pnl(self.trades)

    @property
    def expectancy_usd(self) -> Decimal:
        return expectancy(self.trades)

    @property
    def win_rate_pct(self) -> Decimal:
        return win_rate_pct(self.trades)

    @property
    def equity_curve(self) -> list[Decimal]:
        return equity_curve_from(self.initial_capital_usd, self.trades)

    @property
    def max_drawdown_pct(self) -> Decimal:
        return max_drawdown_pct(self.equity_curve)

    @property
    def final_equity_usd(self) -> Decimal:
        return self.initial_capital_usd + self.net_pnl_usd

    def elapsed_days(self, now: datetime | None = None) -> float:
        """Days since the session first started — not since the last restart."""
        moment = now or datetime.now(timezone.utc)
        return (moment - self.started_at).total_seconds() / 86400

    def to_dict(self) -> dict[str, object]:
        return {
            "token_mint": self.token_mint,
            "strategy_name": self.strategy_name,
            "started_at": self.started_at.isoformat(),
            "initial_capital_usd": str(self.initial_capital_usd),
            "trades": [t.to_dict() for t in self.trades],
            "open_position": (
                {
                    "token_mint": self.open_position.token_mint,
                    "entry_price": str(self.open_position.entry_price),
                    "size_usd": str(self.open_position.size_usd),
                    "opened_at": self.open_position.opened_at.isoformat(),
                }
                if self.open_position
                else None
            ),
            "open_entry_fees_usd": str(self.open_entry_fees_usd),
            "funded_mints": sorted(self.funded_mints),
            "ticks": self.ticks,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
        }

    @staticmethod
    def from_dict(raw: dict) -> PaperSessionState:
        position_raw = raw.get("open_position")
        position = (
            Position(
                token_mint=position_raw["token_mint"],
                entry_price=Decimal(position_raw["entry_price"]),
                size_usd=Decimal(position_raw["size_usd"]),
                opened_at=datetime.fromisoformat(position_raw["opened_at"]),
            )
            if position_raw
            else None
        )
        last_tick = raw.get("last_tick_at")
        return PaperSessionState(
            token_mint=raw["token_mint"],
            strategy_name=raw["strategy_name"],
            started_at=datetime.fromisoformat(raw["started_at"]),
            initial_capital_usd=Decimal(raw["initial_capital_usd"]),
            trades=[ClosedTrade.from_dict(t) for t in raw.get("trades", [])],
            open_position=position,
            open_entry_fees_usd=Decimal(raw.get("open_entry_fees_usd", "0")),
            funded_mints=set(raw.get("funded_mints", [])),
            ticks=int(raw.get("ticks", 0) or 0),
            last_tick_at=datetime.fromisoformat(last_tick) if last_tick else None,
        )


class PaperSessionStore:
    def __init__(self, state_dir: Path | str) -> None:
        self._path = Path(state_dir) / "paper-session.json"

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> PaperSessionState | None:
        if not self._path.is_file():
            return None
        try:
            return PaperSessionState.from_dict(json.loads(self._path.read_text()))
        except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError) as exc:
            # Never silently start a fresh 30-day clock over a corrupt file —
            # that would erase evidence the gate depends on and reset the
            # countdown without anyone noticing.
            raise ValueError(
                f"paper session state at {self._path} is unreadable ({exc}). "
                "Refusing to start a new session over it: move the file aside "
                "deliberately if you intend to restart the validation clock."
            ) from exc

    def save(self, state: PaperSessionState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=2))
        os.replace(tmp, self._path)

    def load_or_start(
        self,
        token_mint: str,
        strategy_name: str,
        initial_capital_usd: Decimal,
        now: datetime | None = None,
    ) -> PaperSessionState:
        """Resume an existing session, or begin a new one.

        A resumed session keeps its original `started_at`, so restarts do
        not extend or reset the 30-day validation window.
        """
        existing = self.load()
        if existing is not None:
            if existing.token_mint != token_mint:
                raise ValueError(
                    f"existing paper session is for {existing.token_mint}, not "
                    f"{token_mint}. Two tokens in one session file would make the "
                    "gate's evidence ambiguous."
                )
            if existing.strategy_name != strategy_name:
                raise ValueError(
                    f"existing paper session ran strategy {existing.strategy_name!r}, "
                    f"not {strategy_name!r}. Changing strategy mid-run invalidates "
                    "the validation window; start a new session file instead."
                )
            return existing

        state = PaperSessionState(
            token_mint=token_mint,
            strategy_name=strategy_name,
            started_at=now or datetime.now(timezone.utc),
            initial_capital_usd=initial_capital_usd,
        )
        self.save(state)
        return state


def with_tick(state: PaperSessionState, at: datetime) -> PaperSessionState:
    return replace(state, ticks=state.ticks + 1, last_tick_at=at)
