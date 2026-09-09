"""Backtest runner: strategy → risk → simulated fill, bar by bar.

The runner exists to produce one number honestly: expectancy *after* fees
and slippage. Every design choice here is subordinate to that.

Three properties make the result trustworthy:

1. **The same risk engine runs.** Position sizing, the slippage cap, stops
   and the daily circuit breaker all apply, exactly as they would live.
   A backtest that skipped them would be measuring a more permissive
   system than the one that trades.
2. **No look-ahead.** The strategy sees `candles[:i+1]` and never index
   `i+1`. Entries and exits fill on the same bar's close that produced the
   signal, adjusted adversely for assumed slippage — never on a later,
   better price.
3. **Isolated state.** Risk state lives in memory per run, so a halt in
   one backtest cannot leak into the next and make results depend on the
   order they were run in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from core.config import RunConfig
from core.logging import get_logger
from core.types import (
    Candle,
    Mode,
    Position,
    Quote,
    Side,
    Signal,
    SignalType,
    TradeIntent,
)
from core.performance import (
    ClosedTrade,
    expectancy,
    gross_pnl,
    max_drawdown_pct,
    net_pnl,
    total_fees,
    win_rate_pct,
)
from execution.costs import CostModel
from execution.fills import FillSimulator
from risk.engine import RiskEngine
from risk.state import InMemoryRiskStateStore
from risk.stops import StopAction
from strategy.base import Strategy

logger = get_logger("tradecc.backtest")

HUNDRED = Decimal(100)


@dataclass
class BacktestResult:
    token_mint: str
    strategy_name: str
    candles_processed: int
    first_candle_at: datetime | None
    last_candle_at: datetime | None
    initial_capital_usd: Decimal
    trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[Decimal] = field(default_factory=list)
    signals_generated: int = 0
    entries_blocked_by_risk: int = 0
    block_reasons: dict[str, int] = field(default_factory=dict)
    open_position_at_end: bool = False

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
        """Average net P&L per trade — the validation gate's number."""
        return expectancy(self.trades)

    @property
    def win_rate_pct(self) -> Decimal:
        return win_rate_pct(self.trades)

    @property
    def max_drawdown_pct(self) -> Decimal:
        return max_drawdown_pct(self.equity_curve)

    @property
    def final_equity_usd(self) -> Decimal:
        return self.initial_capital_usd + self.net_pnl_usd

    @property
    def is_profitable_net(self) -> bool:
        return self.net_pnl_usd > 0


class BacktestRunner:
    def __init__(self, config: RunConfig, strategy: Strategy) -> None:
        self._config = config
        self._strategy = strategy
        self._fills = FillSimulator(CostModel(config.costs))
        # In-memory risk state: a backtest must not inherit or leave behind
        # a circuit-breaker halt.
        self._risk = RiskEngine(config, InMemoryRiskStateStore())

    @property
    def risk(self) -> RiskEngine:
        return self._risk

    def run(self, token_mint: str, candles: Sequence[Candle]) -> BacktestResult:
        result = BacktestResult(
            token_mint=token_mint,
            strategy_name=self._strategy.name,
            candles_processed=len(candles),
            first_candle_at=candles[0].timestamp if candles else None,
            last_candle_at=candles[-1].timestamp if candles else None,
            initial_capital_usd=self._config.backtest.initial_capital_usd,
        )
        if not candles:
            return result

        equity = self._config.backtest.initial_capital_usd
        result.equity_curve.append(equity)

        position: Position | None = None
        entry_fees = Decimal(0)
        # Associated-token-account rent is charged the first time this wallet
        # touches a mint, not on every trade. Charging it per entry overstated
        # costs badly at these sizes.
        funded_mints: set[str] = set()
        start = max(self._strategy.minimum_candles, 1)

        for index in range(start, len(candles) + 1):
            window = candles[:index]
            candle = window[-1]
            signal = self._strategy.generate(token_mint, window)
            result.signals_generated += 1

            if position is None:
                if signal.type is SignalType.BUY:
                    opened = self._try_open(signal, candle, result, funded_mints)
                    if opened is not None:
                        position, entry_fees = opened
            else:
                closed = self._maybe_close(position, entry_fees, signal, candle)
                if closed is not None:
                    result.trades.append(closed)
                    equity += closed.net_pnl_usd
                    # The breaker sees backtest time, not the wall clock, so
                    # daily limits follow the simulated calendar.
                    self._risk.record_realized_pnl(closed.net_pnl_usd, candle.timestamp)
                    position = None
                    entry_fees = Decimal(0)

            result.equity_curve.append(equity)

        result.open_position_at_end = position is not None
        logger.info(
            "backtest_complete",
            extra={
                "token_mint": token_mint,
                "strategy": self._strategy.name,
                "trades": result.trade_count,
                "net_pnl_usd": result.net_pnl_usd,
                "gross_pnl_usd": result.gross_pnl_usd,
                "fees_usd": result.total_fees_usd,
                "max_drawdown_pct": result.max_drawdown_pct,
            },
        )
        return result

    def _try_open(
        self,
        signal: Signal,
        candle: Candle,
        result: BacktestResult,
        funded_mints: set[str],
    ) -> tuple[Position, Decimal] | None:
        size_usd = self._config.risk.position_size_usd
        quote = self._synthetic_quote(signal.token_mint, candle, Side.BUY, size_usd)
        intent = TradeIntent(
            signal=signal, quote=quote, size_usd=size_usd, mode=Mode.BACKTEST
        )

        decision = self._risk.approve(intent, candle.timestamp)
        if not decision.approved:
            result.entries_blocked_by_risk += 1
            for code, _ in decision.rejections:
                result.block_reasons[code.value] = result.block_reasons.get(code.value, 0) + 1
            return None

        creates_account = signal.token_mint not in funded_mints
        fill = self._fills.simulate(
            quote, size_usd, at=candle.timestamp, creates_token_account=creates_account
        )
        funded_mints.add(signal.token_mint)
        position = Position(
            token_mint=signal.token_mint,
            entry_price=fill.price,
            size_usd=size_usd,
            opened_at=candle.timestamp,
        )
        return position, fill.fee_usd

    def _maybe_close(
        self, position: Position, entry_fees: Decimal, signal: Signal, candle: Candle
    ) -> ClosedTrade | None:
        exit_price = self._exit_price(candle)
        # Stops are evaluated on the adverse exit price, not the raw close:
        # that is the price we would actually get out at.
        evaluation = self._risk.evaluate_position(position, exit_price)

        if evaluation.action is StopAction.STOP_LOSS:
            reason = "stop_loss"
        elif evaluation.action is StopAction.TAKE_PROFIT:
            reason = "take_profit"
        elif signal.type is SignalType.SELL:
            reason = signal.metadata.get("reason", "strategy_sell")
        else:
            return None

        exit_fill = self._fills.simulate(
            self._synthetic_quote(
                position.token_mint, candle, Side.SELL, position.size_usd
            ),
            position.size_usd,
            at=candle.timestamp,
            creates_token_account=False,
        )
        return ClosedTrade(
            token_mint=position.token_mint,
            entry_at=position.opened_at,
            exit_at=candle.timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size_usd=position.size_usd,
            fees_usd=entry_fees + exit_fill.fee_usd,
            exit_reason=reason,
        )

    def _synthetic_quote(
        self, token_mint: str, candle: Candle, side: Side, size_usd: Decimal
    ) -> Quote:
        """A quote reconstructed from a historical candle.

        Historical bars carry no quotes, so slippage is assumed rather than
        measured — see `BacktestConfig.assumed_slippage_pct`. The assumption
        is always applied adversely: buys fill higher, sells fill lower.
        """
        slippage = self._config.backtest.assumed_slippage_pct / HUNDRED
        if side is Side.BUY:
            worst_case = candle.close * (Decimal(1) + slippage)
        else:
            worst_case = candle.close * (Decimal(1) - slippage)
        return Quote(
            token_mint=token_mint,
            side=side,
            amount_usd=size_usd,
            expected_price=candle.close,
            worst_case_price=worst_case,
            fee_usd=Decimal(0),
            source="backtest",
        )

    def _exit_price(self, candle: Candle) -> Decimal:
        slippage = self._config.backtest.assumed_slippage_pct / HUNDRED
        return candle.close * (Decimal(1) - slippage)
