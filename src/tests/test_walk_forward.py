"""The walk-forward decision rule must not silently drift.

The harness lives in research/ (an analysis tool, outside the bot and
outside coverage), but its verdict logic decides whether a strategy is
called "replicated", so it is pinned here. A rule that quietly weakened
to pass a result would defeat the entire protocol.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parents[2] / "research"
if str(_RESEARCH) not in sys.path:
    sys.path.insert(0, str(_RESEARCH))

from walk_forward import FoldResult, fold_bounds, judge  # noqa: E402

from core.performance import ClosedTrade  # noqa: E402

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trade(net: Decimal, *, at_hours: int = 0) -> ClosedTrade:
    """A trade with a chosen net P&L and zero fees, for arithmetic clarity."""
    # net = size * (exit - entry) / entry, fees 0. With size=1, entry=1,
    # exit = 1 + net gives exactly `net`.
    return ClosedTrade(
        token_mint="So11111111111111111111111111111111111111112",
        entry_at=BASE + timedelta(hours=at_hours),
        exit_at=BASE + timedelta(hours=at_hours + 1),
        entry_price=Decimal("1"),
        exit_price=Decimal("1") + net,
        size_usd=Decimal("1"),
        fees_usd=Decimal("0"),
        exit_reason="test",
    )


def _fold(index: int, nets: list[str], trades_each_worth=None) -> FoldResult:
    trades = [_trade(Decimal(n)) for n in nets]
    return FoldResult(
        index=index,
        first_candle="2026-01-01",
        last_candle="2026-01-02",
        trades=trades,
    )


def test_fold_bounds_tile_the_series_with_no_gap():
    bounds = fold_bounds(1000, 3)

    assert bounds[0][0] == 0
    assert bounds[-1][1] == 1000
    # Contiguous: each fold starts where the previous ended.
    for (_, hi), (lo, _) in zip(bounds, bounds[1:]):
        assert hi == lo


def test_fold_bounds_final_window_absorbs_the_remainder():
    """1000 / 3 leaves 1 candle; it must land in the last fold, not vanish."""
    bounds = fold_bounds(1000, 3)

    sizes = [hi - lo for lo, hi in bounds]
    assert sum(sizes) == 1000
    assert sizes[-1] == 334  # 333 + the remainder


def test_replicates_only_when_every_condition_holds():
    # Three positive, balanced folds, 12+ trades: the one passing shape.
    folds = [
        _fold(0, ["0.2"] * 5),
        _fold(1, ["0.2"] * 5),
        _fold(2, ["0.2"] * 5),
    ]
    verdict = judge(folds)

    assert verdict.replicated


def test_concentration_fails_when_one_fold_carries_the_result():
    """The 1h Phase A failure mode: pooled positive, but one fold dominates."""
    folds = [
        _fold(0, ["-0.05"] * 4),  # a losing fold
        _fold(1, ["0.5"] * 4),  # carries almost everything
        _fold(2, ["0.02"] * 4),
    ]
    verdict = judge(folds)

    assert verdict.pooled_positive
    assert not verdict.not_concentrated
    assert not verdict.replicated


def test_negative_pool_is_never_replicated_even_with_a_big_positive_fold():
    """The 4h failure mode: two positive folds, one large loss, net negative."""
    folds = [
        _fold(0, ["-1.4"]),
        _fold(1, ["0.8"]),
        _fold(2, ["0.1"]),
    ]
    verdict = judge(folds)

    assert verdict.majority_positive  # 2 of 3 folds positive
    assert not verdict.pooled_positive
    assert not verdict.not_concentrated  # undefined-safe: negative pool -> fail
    assert not verdict.replicated


def test_too_few_trades_blocks_replication_on_its_own():
    folds = [
        _fold(0, ["0.2"] * 3),
        _fold(1, ["0.2"] * 3),
        _fold(2, ["0.2"] * 3),
    ]  # 9 pooled trades, all folds positive and balanced
    verdict = judge(folds)

    assert verdict.majority_positive
    assert verdict.pooled_positive
    assert not verdict.enough_trades
    assert not verdict.replicated


def test_majority_needs_two_of_three_positive_folds():
    folds = [
        _fold(0, ["0.5"] * 6),  # one big positive
        _fold(1, ["-0.05"] * 6),
        _fold(2, ["-0.05"] * 6),
    ]
    verdict = judge(folds)

    assert not verdict.majority_positive
    assert not verdict.replicated
