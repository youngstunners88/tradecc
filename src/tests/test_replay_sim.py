"""The replay simulator's two load-bearing properties.

`trade-simulation` claims the run is deterministic and point-in-time clean.
Both claims are what make a diff in its output mean something, so both are
pinned here rather than left as prose in a skill file.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from core.candles import Candle

ROOT = Path(__file__).resolve().parents[2]


def load_replay_module():
    spec = importlib.util.spec_from_file_location(
        "replay_sim", ROOT / "research" / "replay_sim.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["replay_sim"] = module
    spec.loader.exec_module(module)
    return module


replay = load_replay_module()


def series(n: int = 10) -> list[Candle]:
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [
        Candle(
            timestamp=start + timedelta(minutes=15 * i),
            open=Decimal(100 + i),
            high=Decimal(100 + i),
            low=Decimal(100 + i),
            close=Decimal(100 + i),
            volume=Decimal(1000),
        )
        for i in range(n)
    ]


def test_source_never_serves_a_future_bar():
    """The whole exercise is a lookahead artefact if it does. At tick i the
    trader may see bars 0..i and nothing after."""
    candles = series(10)
    source = replay.ReplayCandleSource(candles, warmup=3)

    for expected_last in range(3, 10):
        window = source.fetch_candles("pool")
        assert window[-1].timestamp == candles[expected_last].timestamp
        assert len(window) == expected_last + 1
        assert all(c.timestamp <= source.now for c in window)
        source.advance()

    assert source.exhausted


def test_limit_takes_the_most_recent_bars_not_the_oldest():
    source = replay.ReplayCandleSource(series(10), warmup=8)
    window = source.fetch_candles("pool", limit=3)
    assert len(window) == 3
    assert window[-1].close == Decimal(108)


def test_now_tracks_the_bar_being_replayed():
    candles = series(10)
    source = replay.ReplayCandleSource(candles, warmup=4)
    assert source.now == candles[4].timestamp
    source.advance()
    assert source.now == candles[5].timestamp


@pytest.mark.skipif(
    not (ROOT / "research" / ".candle-cache").exists(),
    reason="no cached candles on this host",
)
def test_the_same_cache_produces_the_same_result_twice():
    """Determinism is what lets a diff in the report mean 'the code changed'.
    If this ever fails, the simulator has picked up a clock, the network, or
    an unseeded random — and every comparison made with it becomes worthless."""
    pool = "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj"
    if not (ROOT / "research" / ".candle-cache" / f"{pool}_1d.json").is_file():
        pytest.skip("the reference pool is not cached here")

    first_state, first_cov, _ = replay.simulate(pool, "1d", 60, "0.2")
    second_state, second_cov, _ = replay.simulate(pool, "1d", 60, "0.2")

    assert first_cov.actions == second_cov.actions
    assert first_cov.exit_reasons == second_cov.exit_reasons
    assert first_state.net_pnl_usd == second_state.net_pnl_usd
    assert len(first_state.trades) == len(second_state.trades)
