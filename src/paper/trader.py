"""Paper trading: real quotes, simulated fills, nothing sent.

Paper mode is the same loop live mode will run, with exactly one
difference: the fill is simulated instead of signed. Everything before
that point — candles, strategy, real Jupiter quotes, the full risk engine
— is identical. That is what makes 30 days of paper evidence about the
live system rather than about a friendlier imitation of it.

There is no signing, sending, or wallet access anywhere in this module,
and a test asserts the quote source it holds cannot send either.

One tick is one decision. The loop that calls `tick()` lives outside, so
the trader can be tested exhaustively without a clock or a sleep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol, Sequence

from core.config import RunConfig
from core.logging import get_logger
from core.performance import ClosedTrade
from core.telemetry import log_and_track
from core.types import Candle, Mode, Position, Quote, Side, SignalType, TradeIntent
from execution.client import QuoteSource
from execution.costs import CostModel
from execution.fills import FillSimulator
from execution.http import ProviderError
from paper.session import PaperSessionState, PaperSessionStore
from risk.engine import RiskEngine
from risk.state import RiskStateStore
from risk.stops import StopAction
from strategy.base import Strategy

logger = get_logger("tradecc.paper")

HUNDRED = Decimal(100)


class CandleSource(Protocol):
    def fetch_candles(
        self, pool_address: str, interval: str = ..., limit: int = ...
    ) -> list[Candle]: ...


@dataclass(frozen=True)
class TickResult:
    """What one decision cycle did. Never raises past the caller."""

    at: datetime
    action: str
    detail: str = ""
    signal: SignalType | None = None
    trade: ClosedTrade | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class PaperTrader:
    def __init__(
        self,
        config: RunConfig,
        strategy: Strategy,
        quote_source: QuoteSource,
        candle_source: CandleSource,
        store: PaperSessionStore,
    ) -> None:
        if config.mode is Mode.LIVE:
            # Defence in depth: the CLI gates live mode, but nothing should be
            # able to run the paper trader while claiming to be live.
            raise ValueError("PaperTrader must not be constructed in live mode")
        self._config = config
        self._strategy = strategy
        self._quotes = quote_source
        self._candles = candle_source
        self._store = store
        self._fills = FillSimulator(CostModel(config.costs))
        # Disk-backed risk state: a restart must not clear a circuit-breaker
        # halt, which is the opposite of the backtest's requirement.
        self._risk = RiskEngine(config, RiskStateStore(config.state_dir))

    @property
    def risk(self) -> RiskEngine:
        return self._risk

    def tick(self, state: PaperSessionState, now: datetime | None = None) -> TickResult:
        """Run one decision cycle. Provider failures are returned, not raised.

        A 30-day unattended run must survive a bad afternoon at a provider.
        An exception escaping here would end the session and, with it, the
        validation window.
        """
        moment = now or datetime.now(timezone.utc)
        try:
            candles = self._candles.fetch_candles(
                self._config.paper.pool_address,
                self._config.data.candle_interval,
                limit=max(self._strategy.minimum_candles * 2, 100),
            )
        except ProviderError as exc:
            log_and_track(
                "rpc.failure",
                level=logging.WARNING,
                provider=exc.provider,
                resolved=False,
                detail=str(exc),
            )
            return TickResult(moment, "provider_error", error=str(exc))

        if len(candles) < self._strategy.minimum_candles:
            return TickResult(
                moment,
                "insufficient_history",
                detail=f"{len(candles)} candles, need {self._strategy.minimum_candles}",
            )

        signal = self._strategy.generate(state.token_mint, candles)
        price = candles[-1].close

        try:
            if state.open_position is None:
                return self._consider_entry(state, signal, moment)
            return self._consider_exit(state, signal, price, moment)
        except ProviderError as exc:
            log_and_track(
                "rpc.failure",
                level=logging.WARNING,
                provider=exc.provider,
                resolved=False,
                detail=str(exc),
            )
            return TickResult(moment, "provider_error", signal=signal.type, error=str(exc))

    def _consider_entry(
        self, state: PaperSessionState, signal, moment: datetime
    ) -> TickResult:
        if signal.type is not SignalType.BUY:
            return TickResult(moment, "hold", signal=signal.type)

        size_usd = self._config.risk.position_size_usd
        quote = self._live_quote(state.token_mint, Side.BUY, size_usd)
        intent = TradeIntent(signal=signal, quote=quote, size_usd=size_usd, mode=self._config.mode)

        decision = self._risk.approve(intent, moment)
        if not decision.approved:
            return TickResult(
                moment, "entry_blocked", detail=decision.describe(), signal=signal.type
            )

        creates_account = state.token_mint not in state.funded_mints
        fill = self._fills.simulate(
            quote, size_usd, at=moment, creates_token_account=creates_account
        )
        state.funded_mints.add(state.token_mint)
        state.open_position = Position(
            token_mint=state.token_mint,
            entry_price=fill.price,
            size_usd=size_usd,
            opened_at=moment,
        )
        state.open_entry_fees_usd = fill.fee_usd

        log_and_track(
            "trade.simulated",
            token=state.token_mint,
            side=Side.BUY.value,
            size_usd=size_usd,
            modeled_fee_usd=fill.fee_usd,
            modeled_slippage_pct=quote.slippage_pct,
            strategy=self._strategy.name,
        )
        return TickResult(moment, "entered", detail=f"at {fill.price}", signal=signal.type)

    def _consider_exit(
        self, state: PaperSessionState, signal, price: Decimal, moment: datetime
    ) -> TickResult:
        position = state.open_position
        if position is None:
            return TickResult(moment, "hold", signal=signal.type)

        evaluation = self._risk.evaluate_position(position, price)
        if evaluation.action is StopAction.STOP_LOSS:
            reason = "stop_loss"
        elif evaluation.action is StopAction.TAKE_PROFIT:
            reason = "take_profit"
        elif signal.type is SignalType.SELL:
            reason = signal.metadata.get("reason", "strategy_sell")
        else:
            return TickResult(moment, "holding_position", signal=signal.type)

        quote = self._live_quote(state.token_mint, Side.SELL, position.size_usd)
        fill = self._fills.simulate(
            quote, position.size_usd, at=moment, creates_token_account=False
        )
        trade = ClosedTrade(
            token_mint=position.token_mint,
            entry_at=position.opened_at,
            exit_at=moment,
            entry_price=position.entry_price,
            exit_price=fill.price,
            size_usd=position.size_usd,
            fees_usd=state.open_entry_fees_usd + fill.fee_usd,
            exit_reason=reason,
        )
        state.trades.append(trade)
        state.open_position = None
        state.open_entry_fees_usd = Decimal(0)
        self._risk.record_realized_pnl(trade.net_pnl_usd, moment)

        log_and_track(
            "trade.simulated",
            token=state.token_mint,
            side=Side.SELL.value,
            size_usd=position.size_usd,
            modeled_fee_usd=fill.fee_usd,
            modeled_slippage_pct=quote.slippage_pct,
            strategy=self._strategy.name,
            exit_reason=reason,
            net_pnl_usd=trade.net_pnl_usd,
        )
        return TickResult(moment, "exited", detail=reason, signal=signal.type, trade=trade)

    def _live_quote(self, token_mint: str, side: Side, size_usd: Decimal) -> Quote:
        """A real Jupiter quote. Reading a price sends nothing."""
        paper = self._config.paper
        amount_atomic = int(size_usd * (Decimal(10) ** paper.quote_mint_decimals))
        slippage_bps = int(self._config.risk.max_slippage_pct * Decimal(100))

        if side is Side.BUY:
            input_mint, output_mint = paper.quote_mint, token_mint
        else:
            input_mint, output_mint = token_mint, paper.quote_mint

        return self._quotes.get_quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount_atomic=amount_atomic,
            slippage_bps=slippage_bps,
            amount_usd=size_usd,
            side=side,
        )

    def run_tick_and_save(
        self, state: PaperSessionState, now: datetime | None = None
    ) -> TickResult:
        """Tick, then persist — so a crash loses at most one decision."""
        result = self.tick(state, now)
        state.ticks += 1
        state.last_tick_at = result.at
        self._store.save(state)
        return result
