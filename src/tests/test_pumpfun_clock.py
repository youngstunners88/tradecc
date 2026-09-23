"""pump.fun graduation clock: the rules sealed in
planning/decisions/2026-09-13-pumpfun-graduation-duration.md and the
2026-09-23 amendment, pinned. Frozen fixtures; no network by default."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("pumpfun_clock", ROOT / "research" / "pumpfun_clock.py")
pc = importlib.util.module_from_spec(_spec)
sys.modules["pumpfun_clock"] = pc     # dataclasses resolve their module by name
_spec.loader.exec_module(pc)

H = 3600.0
T0 = 1_800_000_000.0          # clock start


def coin(mint, created, pool="P", complete=True):
    return {"mint": mint, "created_timestamp": int(created * 1000), "pump_swap_pool": f"{pool}-{mint}",
            "complete": complete}


def lister(coins, page=pc.PAGE):
    calls = []
    def list_page(offset, limit):
        calls.append(offset)
        return coins[offset:offset + limit]
    return list_page, calls


def state(**kw):
    return pc.ClockState(clock_id="c", t_init=T0, **kw)


# --- sealed parameters -------------------------------------------------------

def test_locked_parameters_match_the_amendment():
    assert pc.FILL_CUTOFF_H == 20.0
    assert pc.POLL_INTERVAL_H == 2.0


def test_both_sealed_records_exist_and_are_hashed_at_init(tmp_path):
    ev = pc.init_event(T0)
    assert set(ev["sealed"]) == set(pc.SEALED)
    assert all(len(h) == 64 for h in ev["sealed"].values())


# --- classification ------------------------------------------------------------

def test_a_fast_fill_after_clock_start_is_in_the_cohort():
    c = pc.Coin("m", T0, "p")
    assert pc.classify(c, T0 + 1 * H, T0) == ("grad", None)


def test_a_graduation_before_clock_start_is_excluded_pre_clock():
    c = pc.Coin("m", T0 - 5 * H, "p")
    assert pc.classify(c, T0 - 1 * H, T0) == ("excluded", "pre_clock")


def test_fill_at_or_over_the_cutoff_is_excluded():
    c = pc.Coin("m", T0, "p")
    assert pc.classify(c, T0 + 20 * H, T0) == ("excluded", "fill_ge_cutoff")
    assert pc.classify(c, T0 + 19.99 * H, T0) == ("grad", None)


def test_graduation_before_creation_is_bad_data_not_a_negative_fill():
    c = pc.Coin("m", T0 + 5 * H, "p")
    assert pc.classify(c, T0 + 1 * H, T0) == ("excluded", "bad_timestamps")


# --- coverage --------------------------------------------------------------------

def test_coverage_complete_when_window_reaches_cutoff_plus_gap():
    ok, hole = pc.coverage(22.5, False, 2.0)
    assert ok and hole is None


def test_coverage_records_a_HOLE_when_the_window_falls_short():
    """A 12h poll gap with a 23h window cannot see fills above 11h."""
    ok, hole = pc.coverage(23.0, False, 12.0)
    assert not ok
    assert hole["needed_h"] == 32.0
    assert hole["uncovered_fill_h"] == [11.0, 20.0]


def test_an_exhausted_listing_is_complete_by_definition():
    ok, _ = pc.coverage(1.0, True, 50.0)
    assert ok


# --- poll ---------------------------------------------------------------------------

def test_poll_records_cohort_and_exclusions_and_never_prices_anything():
    now = T0 + 2 * H
    coins = [coin("fast", T0 + 0.5 * H), coin("pre", T0 - 3 * H)]
    list_page, _ = lister(coins)
    grads = {"P-fast": T0 + 1 * H, "P-pre": T0 - 1 * H}
    evs = pc.poll(state(), list_page, lambda pools: {p: grads[p] for p in pools}, now)
    kinds = [e["kind"] for e in evs]
    assert kinds[0] == "poll"
    assert {e["mint"]: e["kind"] for e in evs[1:]} == {"fast": "grad", "pre": "excluded"}
    assert not any("price" in k or "return" in k for e in evs for k in e)


def test_an_unindexed_pool_is_unresolved_NOT_excluded_and_retried_later():
    """A pool GeckoTerminal has not indexed yet must not be dropped for good."""
    now = T0 + 2 * H
    list_page, _ = lister([coin("new", T0 + 1 * H)])
    evs = pc.poll(state(), list_page, lambda pools: {}, now)
    assert evs[0]["unresolved"] == 1
    assert len(evs) == 1                        # no grad, no excluded


def test_known_mints_are_not_looked_up_again():
    now = T0 + 4 * H
    list_page, _ = lister([coin("a", T0 + 1 * H)])
    looked = []
    pc.poll(state(known={"a"}), list_page, lambda pools: looked.extend(pools) or {}, now)
    assert looked == []


def test_coins_created_too_early_to_ever_qualify_are_not_looked_up():
    """created < prev_poll - cutoff: cannot have graduated since with fill < 20h."""
    prev = T0 + 30 * H
    now = prev + 2 * H
    list_page, _ = lister([coin("old", prev - 21 * H), coin("young", prev - 5 * H)])
    looked = []
    pc.poll(state(last_poll_t=prev), list_page, lambda pools: looked.extend(pools) or {}, now)
    assert looked == ["P-young"]


def test_incomplete_coins_are_ignored():
    list_page, _ = lister([coin("x", T0, complete=False)])
    evs = pc.poll(state(), list_page, lambda p: {}, T0 + H)
    assert evs[0]["listed"] == 0


def test_pagination_stops_at_the_measured_cap():
    many = [coin(f"m{i}", T0 - i) for i in range(5000)]
    list_page, calls = lister(many)
    pc.poll(state(), list_page, lambda p: {}, T0 + H)
    assert max(calls) < pc.MAX_OFFSET


def test_a_short_page_marks_the_listing_exhausted():
    list_page, _ = lister([coin("a", T0)])
    evs = pc.poll(state(), list_page, lambda p: {}, T0 + H)
    assert evs[0]["listing_exhausted"] is True


def test_first_poll_measures_its_gap_from_clock_start():
    list_page, _ = lister([coin(f"m{i}", T0 - i) for i in range(2000)])
    evs = pc.poll(state(), list_page, lambda p: {}, T0 + 2 * H)
    assert evs[0]["prev_t"] == T0


# --- the log: refusals --------------------------------------------------------------

def test_missing_log_refuses_rather_than_starting_a_clock(tmp_path):
    with pytest.raises(pc.ClockError, match="--init"):
        pc.load(tmp_path / "nope.jsonl")


def test_corrupt_line_refuses(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text(json.dumps({"kind": "init", "clock_id": "c", "t": T0}) + "\n{broken\n")
    with pytest.raises(pc.ClockError, match="corrupt"):
        pc.load(f)


def test_unknown_event_kind_refuses(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text(json.dumps({"kind": "init", "clock_id": "c", "t": T0}) + "\n" + json.dumps({"kind": "teleport"}) + "\n")
    with pytest.raises(pc.ClockError, match="unknown event kind"):
        pc.load(f)


def test_first_event_must_be_init(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text(json.dumps({"kind": "poll", "t": T0}) + "\n")
    with pytest.raises(pc.ClockError, match="not init"):
        pc.load(f)


def test_a_second_init_refuses(tmp_path):
    f = tmp_path / "c.jsonl"
    line = json.dumps({"kind": "init", "clock_id": "c", "t": T0})
    f.write_text(line + "\n" + line + "\n")
    with pytest.raises(pc.ClockError, match="one clock"):
        pc.load(f)


def test_a_cohort_mint_recorded_twice_refuses(tmp_path):
    f = tmp_path / "c.jsonl"
    g = json.dumps({"kind": "grad", "mint": "m"})
    f.write_text(json.dumps({"kind": "init", "clock_id": "c", "t": T0}) + f"\n{g}\n{g}\n")
    with pytest.raises(pc.ClockError, match="twice"):
        pc.load(f)


def test_replay_restores_state(tmp_path):
    f = tmp_path / "c.jsonl"
    pc.append(f, [{"kind": "init", "clock_id": "c", "t": T0},
                  {"kind": "poll", "t": T0 + 2 * H, "hole": None},
                  {"kind": "poll", "t": T0 + 4 * H, "hole": {"x": 1}},
                  {"kind": "grad", "mint": "a"}, {"kind": "excluded", "mint": "b"}])
    s = pc.load(f)
    assert (s.polls, s.holes, s.cohort, s.excluded, s.last_poll_t) == (2, 1, 1, 1, T0 + 4 * H)
    assert s.known == {"a", "b"}


def test_init_refuses_when_a_log_already_exists(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text("x\n")
    with pytest.raises(pc.ClockError, match="already exists"):
        pc.main(["--init", "--file", str(f)])


@pytest.mark.network
def test_live_listing_returns_complete_coins_newest_first():
    page = pc.live_list_page(0, 5)
    assert page and all(c["complete"] for c in page)
    ts = [c["created_timestamp"] for c in page]
    assert ts == sorted(ts, reverse=True)
