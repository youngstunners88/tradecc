"""The universe extractor: schema, and the window discipline it rests on.

Merged from two drafts DeepSeek emitted at this same path with different,
partly overlapping coverage. Neither was a superset: the first had the
program-exclusion and blank-pool cases, the second had the selection-window
case — which is the one that matters most, since the window closing before
ranking begins is the single property that makes the whole method mean
anything.

Both drafts imported `research.copy_wallet.*` as a package, which is not
importable here. Research modules are loaded by path, as in
`test_edge_budget.py`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
COPY_WALLET = ROOT / "research" / "copy_wallet"
sys.path.insert(0, str(COPY_WALLET))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, COPY_WALLET / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extract_universe_mod = _load("extract_universe")
extract_universe = extract_universe_mod.extract_universe
KNOWN_PROGRAMS = extract_universe_mod.KNOWN_PROGRAMS
SCHEMA = extract_universe_mod.SCHEMA

START = datetime(2026, 6, 1, tzinfo=timezone.utc)
END = datetime(2026, 6, 30, tzinfo=timezone.utc)


def trade(ts: datetime, trader: str) -> dict[str, Any]:
    return {"block": {"timestamp": ts.isoformat()}, "account": {"trader": trader}}


class FakeClient:
    """Returns exactly what it is told to, including out-of-window rows.

    A fake that honours the window cannot fail the window test — it would
    only prove the fake works. The point of this one is that it does *not*
    filter, so the extractor has to.
    """

    def __init__(self, trades: list[dict[str, Any]]) -> None:
        self._trades = trades
        self.calls: list[tuple[str, datetime, datetime]] = []

    def dex_trades_for_pool(self, pool: str, start: datetime, end: datetime):
        self.calls.append((pool, start, end))
        return self._trades


def test_universe_matches_the_schema_contract() -> None:
    result = extract_universe(["pool1"], START, END, client=FakeClient([trade(START, "w1")]))

    assert result["schema"] == SCHEMA == "tradecc.universe.v1"
    assert result["chain"] == "solana"
    assert result["source"] == "bitquery"
    assert result["pools"] == ["pool1"]
    assert result["filters"] == ["performance_blind only"]
    assert result["candidates"] == ["w1"]
    for key in ("selection_window_start", "selection_window_end", "generated_at", "extractor_commit"):
        assert key in result, f"missing required key {key}"
    json.loads(json.dumps(result))  # must round-trip


def test_candidates_outside_the_selection_window_are_dropped() -> None:
    """The test that matters.

    The window closing before ranking begins is what separates this method
    from a leaderboard. The extractor must enforce it locally rather than
    trusting the API to have honoured the query — so this fake deliberately
    returns rows on both sides of the boundary.
    """
    trades = [
        trade(START - timedelta(seconds=1), "before_window"),
        trade(START, "on_start_boundary"),
        trade(START + timedelta(days=3), "inside"),
        trade(END, "on_end_boundary"),
        trade(END + timedelta(seconds=1), "after_window"),
    ]
    result = extract_universe(["pool1"], START, END, client=FakeClient(trades))

    assert result["candidates"] == ["inside", "on_end_boundary", "on_start_boundary"]
    assert "before_window" not in result["candidates"]
    assert "after_window" not in result["candidates"], (
        "an address first seen after selection_end leaked into the universe — "
        "this is the look-ahead the selection window exists to exclude"
    )


def test_a_trade_with_an_unreadable_timestamp_is_dropped_not_kept() -> None:
    """Unknown must never resolve to include."""
    trades = [
        {"account": {"trader": "no_timestamp"}},
        {"block": {"timestamp": "not-a-date"}, "account": {"trader": "bad_timestamp"}},
        trade(START, "good"),
    ]
    result = extract_universe(["pool1"], START, END, client=FakeClient(trades))
    assert result["candidates"] == ["good"]


def test_known_programs_are_excluded() -> None:
    """Programs may be dropped by a static list. Traders may never be dropped
    for performance — that is the bias this method exists to avoid."""
    program = next(iter(KNOWN_PROGRAMS))
    trades = [trade(START, program), trade(START, "real_wallet")]
    result = extract_universe(["pool1"], START, END, client=FakeClient(trades))
    assert result["candidates"] == ["real_wallet"]


def test_the_window_is_still_passed_to_the_query() -> None:
    """Local enforcement is a backstop, not a replacement: fetching the whole
    history and filtering client-side would work but would be gratuitous."""
    client = FakeClient([trade(START, "w1")])
    extract_universe(["pool1"], START, END, client=client)
    assert client.calls == [("pool1", START, END)]


def test_empty_pool_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        extract_universe([], START, END, client=FakeClient([]))


def test_inverted_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="before"):
        extract_universe(["pool1"], END, START, client=FakeClient([]))


def test_candidates_are_deduplicated_and_sorted() -> None:
    trades = [trade(START, "zeta"), trade(START, "alpha"), trade(START, "zeta")]
    result = extract_universe(["pool1"], START, END, client=FakeClient(trades))
    assert result["candidates"] == ["alpha", "zeta"]
