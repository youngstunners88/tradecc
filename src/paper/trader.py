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
from core.candles import completed_candles
from execution.costs import CostModel, sol_price_from_close
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
        """Run one decision cycle. Failures are returned, not raised.

        A 30-day unattended run must survive a bad afternoon at a provider.
        An exception escaping here would end the session and, with it, the
        validation window.

        This used to catch only `ProviderError`, which is narrower than that
        promise. A stress run over 400 hostile ticks died on the first
        exception of any other type, and several are reachable in a month of
        unattended operation: OSError from the candle cache on a full disk,
        JSONDecodeError from a truncated cache file, ValueError from a
        provider price of zero or a size that rounds to no atomic units,
        InvalidOperation on a pathological decimal.

        So the outer boundary catches broadly — but loudly, at ERROR with the
        exception type, and it returns a distinct `tick_error` action rather
        than something that reads like a normal quiet tick. A run that fails
        every tick still cannot manufacture a passing gate: it produces no
        trades, and `trade_count` must reach MIN_POOLED_TRADES.
        """
        moment = now or datetime.now(timezone.utc)
        try:
            return self._tick_inner(state, moment)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - the session must outlive one bad tick
            logger.exception("tick_failed", extra={"error_type": type(exc).__name__})
            log_and_track(
                "paper.tick_failed",
                level=logging.ERROR,
                error_type=type(exc).__name__,
                detail=str(exc),
            )
            return TickResult(moment, "tick_error", error=f"{type(exc).__name__}: {exc}")

    def _tick_inner(self, state: PaperSessionState, moment: datetime) -> TickResult:
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

        # The provider returns the current, still-forming bar alongside the
        # finished ones. Its "close" is the live price and will change, so
        # acting on it means deciding from a bar that has not happened yet —
        # and it would make paper evidence come from a different process
        # than the backtest that validated the strategy.
        candles = completed_candles(candles, self._config.data.candle_interval, moment)

        if len(candles) < self._strategy.minimum_candles:
            return TickResult(
                moment,
                "insufficient_history",
                detail=f"{len(candles)} completed candles, "
                f"need {self._strategy.minimum_candles}",
            )

        signal = self._strategy.generate(state.token_mint, candles)
        price = candles[-1].close

        try:
            if state.open_position is None:
                return self._consider_entry(state, signal, price, moment)
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
        self, state: PaperSessionState, signal, price: Decimal, moment: datetime
    ) -> TickResult:
        if signal.type is not SignalType.BUY:
            return TickResult(moment, "hold", signal=signal.type)

        size_usd = self._config.risk.position_size_usd
        quote = self._live_quote(state.token_mint, Side.BUY, size_usd)
        creates_account = state.token_mint not in state.funded_mints
        # Estimated before approval, so the risk engine can veto a trade whose
        # modelled cost has gone absurd — see risk/fees.py.
        estimated = self._fills.estimate_costs(
            size_usd,
            creates_token_account=creates_account,
            sol_price_usd=sol_price_from_close(state.token_mint, price),
        )
        intent = TradeIntent(
            signal=signal,
            quote=quote,
            size_usd=size_usd,
            mode=self._config.mode,
            estimated_fee_usd=estimated.total_usd,
        )

        decision = self._risk.approve(intent, moment)
        if not decision.approved:
            return TickResult(
                moment, "entry_blocked", detail=decision.describe(), signal=signal.type
            )

        fill = self._fills.simulate(
            quote,
            size_usd,
            at=moment,
            creates_token_account=creates_account,
            sol_price_usd=sol_price_from_close(state.token_mint, price),
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

        quote = self._live_quote(
            state.token_mint, Side.SELL, position.size_usd, entry_price=position.entry_price
        )
        fill = self._fills.simulate(
            quote,
            position.size_usd,
            at=moment,
            creates_token_account=False,
            sol_price_usd=sol_price_from_close(state.token_mint, price),
        )
        # An exit is never blocked on cost. The fee check vetoes entries, but
        # refusing to close a position because closing it looks expensive
        # leaves the bot holding risk it decided to shed — strictly worse. It
        # is still worth saying loudly, because it means the price feed
        # driving the cost model has probably gone wrong.
        fee_cap = position.size_usd * self._config.risk.max_fee_fraction_of_size
        if fill.fee_usd > fee_cap:
            log_and_track(
                "risk.exit_cost_implausible",
                level=logging.ERROR,
                token=state.token_mint,
                modeled_fee_usd=fill.fee_usd,
                size_usd=position.size_usd,
                detail="exiting anyway; check the SOL price feed",
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

    def _live_quote(
        self,
        token_mint: str,
        side: Side,
        size_usd: Decimal,
        entry_price: Decimal | None = None,
    ) -> Quote:
        """A real Jupiter quote. Reading a price sends nothing.

        The input amount must be denominated in the INPUT mint. A BUY spends
        the quote asset, so `size_usd` scaled by `quote_mint_decimals` is
        right. A SELL sends the token, so it must be the token quantity held,
        scaled by the token's own decimals.

        This previously used the quote-asset form for both. On the configured
        SOL/USDC pair that asked Jupiter to price selling 0.01 SOL when the
        position held 0.098 — a 9.8x understatement, and worse on any token
        whose price and decimals differ further from USDC's. Exit prices in
        paper therefore came from a quote for a trade that was not the one
        being simulated, and paper P&L is the evidence the 30-day gate rests
        on.
        """
        paper = self._config.paper
        slippage_bps = int(self._config.risk.max_slippage_pct * Decimal(100))

        if side is Side.BUY:
            input_mint, output_mint = paper.quote_mint, token_mint
            input_decimals, output_decimals = (
                paper.quote_mint_decimals,
                paper.token_mint_decimals,
            )
            amount_atomic = int(size_usd * (Decimal(10) ** paper.quote_mint_decimals))
        else:
            input_mint, output_mint = token_mint, paper.quote_mint
            input_decimals, output_decimals = (
                paper.token_mint_decimals,
                paper.quote_mint_decimals,
            )
            if entry_price is None or entry_price <= 0:
                raise ValueError("a SELL quote needs the entry price to size the token amount")
            quantity = size_usd / entry_price
            amount_atomic = int(quantity * (Decimal(10) ** paper.token_mint_decimals))

        if amount_atomic <= 0:
            # A position small enough to round to zero atomic units cannot be
            # priced, and asking anyway returns a quote for a different trade.
            raise ValueError(
                f"{side.value} size {size_usd} rounds to zero atomic units at "
                f"{input_decimals} decimals — too small to quote"
            )

        return self._quotes.get_quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount_atomic=amount_atomic,
            slippage_bps=slippage_bps,
            amount_usd=size_usd,
            input_decimals=input_decimals,
            output_decimals=output_decimals,
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
