"""Paper mode — real quotes, simulated fills, and nothing sent."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.config import (
    BacktestConfig,
    CostsConfig,
    DataConfig,
    PaperConfig,
    RiskConfig,
    RunConfig,
    StrategyConfig,
)
from core.performance import ClosedTrade
from core.types import Candle, Mode, Position, Side
from execution.http import ProviderError
from execution.mock import MockQuoteSource
from paper.session import PaperSessionState, PaperSessionStore
from paper.trader import PaperTrader
from strategy.strategy_momentum import MomentumParams, MomentumStrategy

TOKEN = "So11111111111111111111111111111111111111112"
POOL = "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def candles(prices) -> list[Candle]:
    """A series whose final bar *closes* exactly at START.

    Paper mode discards bars that have not finished by `now`, so a series
    laid out forward from START would be entirely in progress at
    `now=START` and correctly ignored. Ending the series at START is what
    a real poll returns: history behind you, nothing from the future.
    """
    last = len(prices)
    return [
        Candle(
            timestamp=START - timedelta(minutes=15 * (last - i)),
            open=Decimal(str(p)),
            high=Decimal(str(p)),
            low=Decimal(str(p)),
            close=Decimal(str(p)),
            volume=Decimal("1000"),
        )
        for i, p in enumerate(prices)
    ]


class FakeCandleSource:
    def __init__(self, series: list[Candle] | Exception) -> None:
        self.series = series
        self.calls = 0

    def fetch_candles(self, pool_address, interval="15m", limit=100):
        self.calls += 1
        if isinstance(self.series, Exception):
            raise self.series
        return self.series


class ExplodingQuoteSource:
    def get_quote(self, **kwargs):
        raise ProviderError("jupiter", "service unavailable")


@pytest.fixture
def config(tmp_path) -> RunConfig:
    return RunConfig(
        mode=Mode.PAPER,
        risk=RiskConfig(
            position_size_usd=Decimal("10"),
            max_slippage_pct=Decimal("0.5"),
            daily_loss_limit_usd=Decimal("20"),
            per_trade_stop_loss_pct=Decimal("5"),
            per_trade_take_profit_pct=Decimal("10"),
        ),
        strategy=StrategyConfig(name="momentum", token_mints=(TOKEN,)),
        data=DataConfig(candle_interval="15m"),
        costs=CostsConfig(sol_price_usd=Decimal("200")),
        backtest=BacktestConfig(initial_capital_usd=Decimal("100")),
        paper=PaperConfig(pool_address=POOL),
        state_dir=tmp_path / "state",
        gate_file=tmp_path / "gate.json",
    )


@pytest.fixture
def strategy() -> MomentumStrategy:
    return MomentumStrategy(
        MomentumParams(fast_ema=3, slow_ema=6, rsi_period=5, rsi_overbought=Decimal("70"))
    )


BUY_SERIES = [100, 98, 96, 94, 92, 90, 88, 86, 88, 92, 96]


def trader(config, strategy, series, quotes=None) -> tuple[PaperTrader, PaperSessionStore]:
    store = PaperSessionStore(config.state_dir)
    return (
        PaperTrader(
            config=config,
            strategy=strategy,
            quote_source=quotes or MockQuoteSource(slippage_pct=Decimal("0.2")),
            candle_source=FakeCandleSource(series),
            store=store,
        ),
        store,
    )


def fresh_state(store: PaperSessionStore) -> PaperSessionState:
    return store.load_or_start(TOKEN, "momentum", Decimal("100"), now=START)


# --- session persistence ---


def test_session_starts_and_persists(config):
    store = PaperSessionStore(config.state_dir)

    state = store.load_or_start(TOKEN, "momentum", Decimal("100"), now=START)

    assert store.path.is_file()
    assert state.started_at == START


def test_resuming_keeps_the_original_start_time(config):
    """A restart must not reset or extend the 30-day validation window."""
    store = PaperSessionStore(config.state_dir)
    store.load_or_start(TOKEN, "momentum", Decimal("100"), now=START)

    resumed = store.load_or_start(TOKEN, "momentum", Decimal("100"), now=START + timedelta(days=9))

    assert resumed.started_at == START
    assert resumed.elapsed_days(START + timedelta(days=9)) == pytest.approx(9.0)


def test_session_round_trips_trades_and_position(config):
    store = PaperSessionStore(config.state_dir)
    state = fresh_state(store)
    state.open_position = Position(TOKEN, Decimal("101.5"), Decimal("10"), START)
    state.open_entry_fees_usd = Decimal("0.41")
    state.trades.append(
        ClosedTrade(TOKEN, START, START + timedelta(hours=1), Decimal("100"),
                    Decimal("103"), Decimal("10"), Decimal("0.42"), "take_profit")
    )
    state.funded_mints.add(TOKEN)
    store.save(state)

    reloaded = store.load()

    assert reloaded.open_position.entry_price == Decimal("101.5")
    assert reloaded.open_entry_fees_usd == Decimal("0.41")
    assert reloaded.trades[0].exit_reason == "take_profit"
    assert reloaded.funded_mints == {TOKEN}


def test_corrupt_session_refuses_rather_than_restarting_the_clock(config):
    """Silently starting over would erase the gate's evidence."""
    store = PaperSessionStore(config.state_dir)
    fresh_state(store)
    store.path.write_text("{ not json")

    with pytest.raises(ValueError, match="Refusing to start a new session"):
        store.load_or_start(TOKEN, "momentum", Decimal("100"))


def test_changing_token_mid_session_is_refused(config):
    store = PaperSessionStore(config.state_dir)
    fresh_state(store)

    with pytest.raises(ValueError, match="not"):
        store.load_or_start("OtherMint", "momentum", Decimal("100"))


def test_changing_strategy_mid_session_is_refused(config):
    store = PaperSessionStore(config.state_dir)
    fresh_state(store)

    with pytest.raises(ValueError, match="invalidates"):
        store.load_or_start(TOKEN, "copytrade", Decimal("100"))


def test_session_metrics_match_the_backtest_implementations(config):
    store = PaperSessionStore(config.state_dir)
    state = fresh_state(store)
    state.trades.append(
        ClosedTrade(TOKEN, START, START + timedelta(hours=1), Decimal("100"),
                    Decimal("105"), Decimal("10"), Decimal("0.42"), "take_profit")
    )

    assert state.gross_pnl_usd == Decimal("0.5")
    assert state.net_pnl_usd == Decimal("0.08")
    assert state.expectancy_usd == Decimal("0.08")
    assert state.win_rate_pct == Decimal("100")


# --- trading behaviour ---


def test_tick_opens_a_position_on_a_buy_signal(config, strategy):
    paper, store = trader(config, strategy, candles(BUY_SERIES))
    state = fresh_state(store)

    result = paper.tick(state, now=START)

    assert result.action == "entered"
    assert state.open_position is not None


def test_tick_holds_when_there_is_no_signal(config, strategy):
    flat = candles([100] * 12)
    paper, store = trader(config, strategy, flat)
    state = fresh_state(store)

    result = paper.tick(state, now=START)

    assert result.action in {"hold", "holding_position"}
    assert state.open_position is None


def test_tick_waits_for_enough_history(config, strategy):
    paper, store = trader(config, strategy, candles([100, 101]))
    state = fresh_state(store)

    result = paper.tick(state, now=START)

    assert result.action == "insufficient_history"


def test_entry_uses_a_real_quote(config, strategy):
    """Paper prices against the live venue; only the fill is simulated."""
    quotes = MockQuoteSource(slippage_pct=Decimal("0.2"))
    paper, store = trader(config, strategy, candles(BUY_SERIES), quotes=quotes)
    state = fresh_state(store)

    paper.tick(state, now=START)

    call = quotes.calls[0]
    assert call.side is Side.BUY
    assert call.amount_usd == Decimal("10")
    # $10 of USDC at 6 decimals.
    assert call.amount_atomic == 10_000_000
    assert call.slippage_bps == 50


def test_risk_can_block_a_paper_entry(config, strategy):
    """The same cap that would block a live trade blocks a paper one."""
    quotes = MockQuoteSource(slippage_pct=Decimal("5"))
    paper, store = trader(config, strategy, candles(BUY_SERIES), quotes=quotes)
    state = fresh_state(store)

    result = paper.tick(state, now=START)

    assert result.action == "entry_blocked"
    assert "slippage_exceeded" in result.detail
    assert state.open_position is None


def test_exit_closes_and_records_a_trade(config, strategy):
    paper, store = trader(config, strategy, candles(BUY_SERIES))
    state = fresh_state(store)
    state.open_position = Position(TOKEN, Decimal("200"), Decimal("10"), START)
    state.open_entry_fees_usd = Decimal("0.41")

    result = paper.tick(state, now=START + timedelta(minutes=15))

    assert result.action == "exited"
    assert result.trade is not None
    assert state.open_position is None
    assert state.trades[0].exit_reason == "stop_loss"


def test_closed_trade_carries_both_legs_of_fees(config, strategy):
    paper, store = trader(config, strategy, candles(BUY_SERIES))
    state = fresh_state(store)
    state.open_position = Position(TOKEN, Decimal("200"), Decimal("10"), START)
    state.open_entry_fees_usd = Decimal("0.41")

    paper.tick(state, now=START + timedelta(minutes=15))

    assert state.trades[0].fees_usd > Decimal("0.41")


def test_provider_failure_does_not_end_the_session(config, strategy):
    """A 30-day run must survive a bad afternoon at a provider."""
    paper, store = trader(config, strategy, ProviderError("geckoterminal", "503"))
    state = fresh_state(store)

    result = paper.tick(state, now=START)

    assert result.action == "provider_error"
    assert not result.ok
    assert result.error is not None


def test_quote_failure_does_not_end_the_session(config, strategy):
    paper, store = trader(
        config, strategy, candles(BUY_SERIES), quotes=ExplodingQuoteSource()
    )
    state = fresh_state(store)

    result = paper.tick(state, now=START)

    assert result.action == "provider_error"
    assert state.open_position is None


def test_tick_persists_state_so_a_crash_loses_at_most_one_decision(config, strategy):
    paper, store = trader(config, strategy, candles(BUY_SERIES))
    state = fresh_state(store)

    paper.run_tick_and_save(state, now=START)

    reloaded = store.load()
    assert reloaded.ticks == 1
    assert reloaded.open_position is not None


def test_position_survives_a_restart(config, strategy):
    paper, store = trader(config, strategy, candles(BUY_SERIES))
    state = fresh_state(store)
    paper.run_tick_and_save(state, now=START)

    # A restart is a fresh store over the same directory.
    resumed = PaperSessionStore(config.state_dir).load_or_start(
        TOKEN, "momentum", Decimal("100")
    )

    assert resumed.open_position is not None
    assert resumed.open_position.entry_price == state.open_position.entry_price


def test_circuit_breaker_state_persists_across_restarts(config, strategy):
    """Unlike a backtest, paper must NOT clear a halt on restart."""
    paper, store = trader(config, strategy, candles(BUY_SERIES))
    paper.risk.record_realized_pnl(Decimal("-25"), START)

    restarted, _ = trader(config, strategy, candles(BUY_SERIES))

    assert restarted.risk.circuit_breaker.state(START).halted


def test_trader_refuses_to_be_constructed_in_live_mode(config, strategy):
    live = config.model_copy(update={"mode": Mode.LIVE})

    with pytest.raises(ValueError, match="live mode"):
        PaperTrader(
            config=live,
            strategy=strategy,
            quote_source=MockQuoteSource(),
            candle_source=FakeCandleSource([]),
            store=PaperSessionStore(config.state_dir),
        )


def test_paper_fills_are_never_real(config, strategy):
    paper, store = trader(config, strategy, candles(BUY_SERIES))
    state = fresh_state(store)
    state.open_position = Position(TOKEN, Decimal("200"), Decimal("10"), START)

    result = paper.tick(state, now=START + timedelta(minutes=15))

    # No transaction signature can exist, because nothing was sent.
    assert result.trade is not None
    assert not hasattr(result.trade, "tx_signature")


def test_quote_source_used_by_paper_cannot_send():
    """Structural guarantee: the quote protocol has no send method."""
    from execution.client import QuoteSource
    from execution.jupiter import JupiterQuoteClient

    surface = {n for n in dir(JupiterQuoteClient) if not n.startswith("_")}

    assert surface == {"get_quote", "get_quote_detailed"}
    assert isinstance(MockQuoteSource(), QuoteSource)


def test_an_in_progress_bar_is_ignored(config, strategy):
    """The still-forming bar must not influence the decision.

    Its "close" is just the live price and will keep changing, so acting
    on it means deciding from a bar that has not happened yet — and it
    would make paper evidence come from a different process than the
    backtest that validated the strategy.
    """
    settled = candles(BUY_SERIES)
    # A bar opening exactly at START has not closed by START.
    forming = settled + [
        Candle(
            timestamp=START,
            open=Decimal("999"),
            high=Decimal("999"),
            low=Decimal("999"),
            close=Decimal("999"),
            volume=Decimal("1000"),
        )
    ]

    without, store_a = trader(config, strategy, settled)
    with_forming, store_b = trader(config, strategy, forming)

    clean = without.tick(fresh_state(store_a), now=START)
    noisy = with_forming.tick(fresh_state(store_b), now=START)

    assert noisy.action == clean.action
    assert noisy.signal == clean.signal


def test_only_in_progress_bars_means_insufficient_history(config, strategy):
    """No completed bars is no basis for a decision, not a fallback."""
    forming = [
        Candle(
            timestamp=START + timedelta(minutes=15 * i),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        )
        for i in range(10)
    ]

    paper, store = trader(config, strategy, forming)
    result = paper.tick(fresh_state(store), now=START)

    assert result.action == "insufficient_history"
    assert result.trade is None


def test_sell_quote_is_sized_in_the_token_held_not_the_quote_asset(config, strategy):
    """A SELL sends the TOKEN as input, so amount_atomic must be the token
    quantity in the token's decimals.

    This used to reuse the BUY form — size_usd scaled by quote_mint_decimals —
    which on SOL/USDC asked Jupiter to price selling 0.01 SOL for a position
    holding 0.098. Exit prices in paper then came from a quote for a different
    trade than the one simulated, and paper P&L is what the 30-day gate rests
    on.
    """
    from decimal import Decimal

    from core.types import Side

    captured: dict = {}

    mock = MockQuoteSource(slippage_pct=Decimal("0.2"))

    class CapturingQuotes:
        def get_quote(self, **kwargs):
            captured.update(kwargs)
            return mock.get_quote(**kwargs)

    paper_trader, _ = trader(config, strategy, candles([100, 101]), quotes=CapturingQuotes())

    entry_price = Decimal("101.79")
    size_usd = Decimal("10")
    paper_trader._live_quote(TOKEN, Side.SELL, size_usd, entry_price=entry_price)

    expected_quantity = size_usd / entry_price
    decimals = config.paper.token_mint_decimals
    assert captured["amount_atomic"] == int(expected_quantity * (Decimal(10) ** decimals))
    assert captured["input_mint"] == TOKEN

    # The old, wrong value, pinned so a regression is unambiguous.
    wrong = int(size_usd * (Decimal(10) ** config.paper.quote_mint_decimals))
    assert captured["amount_atomic"] != wrong


def test_sell_quote_refuses_without_an_entry_price(config, strategy):
    """Silently falling back to a USD-shaped amount is what caused the bug."""
    import pytest as _pytest
    from decimal import Decimal

    from core.types import Side

    paper_trader, _ = trader(config, strategy, candles([100, 101]))
    with _pytest.raises(ValueError):
        paper_trader._live_quote(TOKEN, Side.SELL, Decimal("10"))
