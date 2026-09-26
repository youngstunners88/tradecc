"""The closed-category ledger as data — and the guard that keeps it honest.

Transcribing this ledger out of prose immediately found two citations that
did not resolve: copy-trading and pump.fun both pointed at
`planning/decisions/` records that were never written, while the evidence sat
in `research/backtests/`. That is precisely the failure the inventory skill
warns about — a verdict nobody can check.

`test_every_citation_resolves` exists so the next one fails CI rather than
waiting to be stumbled on.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "research" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


inv = _load("edge_inventory")


# --- the guard that earns this module's existence --------------------------


def test_every_citation_resolves() -> None:
    """A ledger whose citations do not resolve is an undocumented verdict
    wearing a citation's clothes."""
    broken = inv.validate_citations()
    assert broken == [], f"citations do not resolve: {broken}"


def test_the_ledger_covers_every_category_the_skill_lists() -> None:
    assert len(inv.LEDGER) == 8, (
        "the skill's ledger has eight categories; if one was added there, add "
        "it here too or the data and the prose disagree"
    )


def test_every_category_names_a_cause_or_says_why_not() -> None:
    """Seven collapse into the four causes. Funding-rate carry is the one
    closed by scope rather than impossibility, and must say so rather than
    being forced into a cause it does not belong to."""
    for cat in inv.LEDGER:
        if cat.cause is None:
            assert "scope" in cat.reason.lower() or "capital" in cat.reason.lower()
        else:
            assert cat.cause in inv.CAUSES, f"{cat.name} names an unknown cause"


def test_funding_carry_is_the_only_one_closed_by_scope() -> None:
    """It is the only row an extra zero on the account size would reopen, and
    that distinction is worth keeping true."""
    scope_closed = [c.name for c in inv.LEDGER if c.cause is None]
    assert scope_closed == ["Funding-rate carry / basis"]


def test_every_category_states_a_reopening_condition() -> None:
    """A closure with no stated reopening condition is a permanent verdict by
    accident rather than by decision."""
    for cat in inv.LEDGER:
        assert cat.reopens_when.strip(), f"{cat.name} has no reopening condition"


# --- lookup must never be mistaken for a ruling ----------------------------


def test_lookup_never_returns_a_verdict() -> None:
    for idea in ("copy trading", "something nobody has ever tried", ""):
        assert inv.lookup(idea)["is_this_a_verdict"] is False


def test_zero_matches_is_explicitly_not_a_clearance() -> None:
    """The dangerous failure mode: reading 'no matches' as 'it's new'."""
    result = inv.lookup("weather derivatives priced off satellite imagery")
    assert result["keyword_matches"] == []
    guidance = result["what_you_must_still_do"]
    assert "does not mean the idea is new" in guidance
    assert "edge-viability-check" in guidance


def test_a_known_category_is_matched_with_its_reason_and_citation() -> None:
    result = inv.lookup("follow smart money wallets and copy their trades")
    names = [m["category"] for m in result["keyword_matches"]]
    assert "Copy-trading (rigorous)" in names
    match = next(m for m in result["keyword_matches"] if m["category"] == "Copy-trading (rigorous)")
    assert match["verdict"] == "Blocked"
    assert "Data infrastructure" in match["cause"]
    assert match["citations"], "a match must carry its evidence"
    assert match["reopens_when"]


def test_directional_ideas_are_caught_by_their_common_vocabulary() -> None:
    """Directional prediction is closed as a CLASS, so the common ways someone
    phrases a new directional idea should surface it."""
    for phrasing in (
        "an EMA crossover strategy",
        "predict the direction of the next move",
        "a momentum signal on 4h bars",
        "RSI mean reversion",
    ):
        names = [m["category"] for m in inv.lookup(phrasing)["keyword_matches"]]
        assert "Directional prediction" in names, f"missed: {phrasing}"


def test_the_standing_position_is_carried_in_every_response() -> None:
    """Nothing is left on the ledger; a caller should not have to already know
    that to interpret an empty match list."""
    result = inv.lookup("anything at all")
    assert "Nothing is left" in result["standing_position"]
    assert "user's call" in result["standing_position"]


def test_the_four_causes_are_returned_so_the_escape_question_can_be_answered() -> None:
    causes = inv.lookup("x")["the_four_causes"]
    assert set(causes) == {"latency", "adverse_selection", "data", "detection_floor"}
