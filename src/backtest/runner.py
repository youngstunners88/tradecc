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

from core.candles import interval_duration
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
from execution.costs import CostModel, sol_price_from_close
from execution.fills import FillSimulator
from risk.engine import RiskEngine
from risk.state import InMemoryRiskStateStore
from risk.stops import StopAction, stop_loss_price, take_profit_price
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
        # A bar's close price is not knowable until the bar ends, so a
        # decision taken from it belongs at the bar's close time, not its
        # open. Stamping it at the open backdates every trade by one full
        # interval and buckets the daily circuit breaker on the wrong day.
        self._bar = interval_duration(config.data.candle_interval)
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

        # Take the bar duration from the data, not from config. Config's
        # interval tells the *fetcher* what to request; a caller replaying a
        # 1h series under a 15m config would otherwise stamp decisions on
        # boundaries no bar has, silently. The series is the authority on
        # how long its own bars are.
        if len(candles) >= 2:
            self._bar = candles[1].timestamp - candles[0].timestamp

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
                    self._risk.record_realized_pnl(
                        closed.net_pnl_usd, self._decision_at(candle)
                    )
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

        decision_at = self._decision_at(candle)
        decision = self._risk.approve(intent, decision_at)
        if not decision.approved:
            result.entries_blocked_by_risk += 1
            for code, _ in decision.rejections:
                result.block_reasons[code.value] = result.block_reasons.get(code.value, 0) + 1
            return None

        creates_account = signal.token_mint not in funded_mints
        fill = self._fills.simulate(
            quote,
            size_usd,
            at=decision_at,
            creates_token_account=creates_account,
            sol_price_usd=self._sol_price_at(signal.token_mint, candle),
        )
        funded_mints.add(signal.token_mint)
        position = Position(
            token_mint=signal.token_mint,
            entry_price=fill.price,
            size_usd=size_usd,
            opened_at=decision_at,
        )
        return position, fill.fee_usd

    def _maybe_close(
        self, position: Position, entry_fees: Decimal, signal: Signal, candle: Candle
    ) -> ClosedTrade | None:
        # Stops are checked against the bar's intrabar extremes, not just its
        # close. A stop hit mid-bar that recovered by the close is a real
        # loss the position would have taken; scoring only the close silently
        # skips it and flatters the strategy. Triggering uses the raw high/low
        # (did the market actually reach the level?) while the fill is marked
        # at the level itself, adjusted adversely.
        # The risk engine still makes the call; it is simply asked about the
        # extremes the bar actually reached rather than only its close.
        stop_hit = (
            self._risk.evaluate_position(position, candle.low).action
            is StopAction.STOP_LOSS
        )
        take_hit = (
            self._risk.evaluate_position(position, candle.high).action
            is StopAction.TAKE_PROFIT
        )

        if stop_hit:
            # Stop first when one bar spans both thresholds: OHLC cannot say
            # which came first, so assume the adverse one.
            reason = "stop_loss"
            raw_exit = stop_loss_price(position, self._config.risk)
        elif take_hit:
            reason = "take_profit"
            raw_exit = take_profit_price(position, self._config.risk)
        elif signal.type is SignalType.SELL:
            reason = signal.metadata.get("reason", "strategy_sell")
            raw_exit = candle.close
        else:
            return None

        exit_price = self._adverse(raw_exit)

        exit_fill = self._fills.simulate(
            self._synthetic_quote(
                position.token_mint, candle, Side.SELL, position.size_usd
            ),
            position.size_usd,
            at=self._decision_at(candle),
            creates_token_account=False,
            sol_price_usd=self._sol_price_at(position.token_mint, candle),
        )
        return ClosedTrade(
            token_mint=position.token_mint,
            entry_at=position.opened_at,
            exit_at=self._decision_at(candle),
            entry_price=position.entry_price,
            exit_price=exit_price,
            size_usd=position.size_usd,
            fees_usd=entry_fees + exit_fill.fee_usd,
            exit_reason=reason,
        )

    def _decision_at(self, candle: Candle) -> datetime:
        """When this bar's close became known — the real decision time."""
        return candle.timestamp + self._bar

    def _sol_price_at(self, token_mint: str, candle: Candle) -> Decimal | None:
        return sol_price_from_close(token_mint, candle.close)

    def _synthetic_quote(
        self, token_mint: str, candle: Candle, side: Side, size_usd: Decimal
    ) -> Quote:
        """A quote reconstructed from a historical candle.

        Historical bars carry no quotes, so the adverse move is applied as
        a constant — but it is now the sum of a *measured* price-impact
        component and an assumed execution-slippage one, rather than a
        single invented number. See `BacktestConfig`. Always applied
        adversely: buys fill higher, sells fill lower.
        """
        adverse = self._config.backtest.total_adverse_pct / HUNDRED
        if side is Side.BUY:
            worst_case = candle.close * (Decimal(1) + adverse)
        else:
            worst_case = candle.close * (Decimal(1) - adverse)
        return Quote(
            token_mint=token_mint,
            side=side,
            amount_usd=size_usd,
            expected_price=candle.close,
            worst_case_price=worst_case,
            fee_usd=Decimal(0),
            source="backtest",
        )

    def _adverse(self, price: Decimal) -> Decimal:
        """A sell marked down by the total adverse move.

        Applies to whatever level we actually exited at — a stop level, a
        take-profit level, or the close — not only to the close.
        """
        adverse = self._config.backtest.total_adverse_pct / HUNDRED
        return price * (Decimal(1) - adverse)
