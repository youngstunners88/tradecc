"""The structural-edge ledger as data, so its citations can be checked.

`.claude/skills/structural-edge-inventory` holds this ledger in prose, and
prose is where a broken citation hides. Transcribing it into data immediately
surfaced two: the copy-trading and pump.fun rows both cited
`planning/decisions/` records that were never written, while the evidence
actually sits in `research/backtests/`. A ledger whose citations do not
resolve is the exact failure the skill itself warns about — "an undocumented
verdict is one nobody can check and everybody can accidentally repeat."

`test_edge_inventory.py` now asserts every citation resolves, so the next
broken one fails CI instead of waiting to be stumbled on.

**This module does not decide whether an idea is new.** `lookup()` returns
keyword *hints* and the ledger, never a verdict. The skill's rule stands and
is a human judgement: name the category, name the cause it must escape, and
say how it escapes. "It feels different" is not an escape, and neither is
"the keyword matcher found nothing".

    PYTHONPATH=src .venv/bin/python research/edge_inventory.py --idea "funding rate carry"
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Cause:
    key: str
    name: str
    description: str


# The four causes every closed category collapses into. A candidate is not new
# if it lands in one of these.
CAUSES: dict[str, Cause] = {
    "latency": Cause(
        "latency",
        "Latency / infrastructure race",
        "Lost to co-located professionals before we start.",
    ),
    "adverse_selection": Cause(
        "adverse_selection",
        "Adverse selection",
        "Being the passive side means being picked off by whoever is faster.",
    ),
    "data": Cause(
        "data",
        "Data infrastructure",
        "The signal may exist; we cannot obtain point-in-time-clean data to "
        "test it at our access level.",
    ),
    "detection_floor": Cause(
        "detection_floor",
        "Detection floor",
        "The edge is smaller than the measurement can resolve at our size.",
    ),
}


@dataclass(frozen=True)
class Category:
    name: str
    verdict: str
    cause: str
    reason: str
    citations: tuple[str, ...]
    reopens_when: str
    keywords: tuple[str, ...] = field(default=())


LEDGER: tuple[Category, ...] = (
    Category(
        name="Cross-DEX arbitrage",
        verdict="Rejected",
        cause="latency",
        reason="Latency race; dominated by professional, co-located, low-latency operators.",
        citations=("planning/decisions/2026-09-09-strategy-and-stack.md",),
        reopens_when="Not realistically — the race is structural.",
        keywords=("arbitrage", "arb", "cross-dex", "cross dex", "spread between venues"),
    ),
    Category(
        name="Sniping new launches",
        verdict="Rejected",
        cause="latency",
        reason="Same latency race, plus MEV exposure.",
        citations=("planning/decisions/2026-09-09-strategy-and-stack.md",),
        reopens_when="Not realistically — the race is structural.",
        keywords=("snipe", "sniping", "new launch", "launch", "mev", "first buyer"),
    ),
    Category(
        name="Copy-trading (rigorous)",
        verdict="Blocked",
        cause="data",
        reason=(
            "Data infrastructure, not economics — point-in-time-clean wallet "
            "enumeration needs ~9,982h at the cheapest pool's measured 0.41 tx/s."
        ),
        # Corrected 2026-09-20: the ledger cited a decision record that does
        # not exist. The measurement is in the feasibility probe.
        citations=("research/backtests/2026-09-12_copy-trading-feasibility-probe.md",),
        reopens_when=(
            "Paid, historical, point-in-time-clean data — which makes it "
            "TESTABLE, not known-good. A Bitquery-based reopen is in progress "
            "on PR #14 and its own viability gate did not pass."
        ),
        keywords=("copy", "copy-trading", "wallet following", "follow wallet", "smart money"),
    ),
    Category(
        name="pump.fun graduation timing",
        verdict="Parked",
        cause="data",
        reason=(
            "Data infrastructure — the historical middle window is unreachable; "
            "only forward collection works, a weeks-long commitment that was declined."
        ),
        # Corrected 2026-09-20: same broken-citation class as copy-trading.
        citations=("research/backtests/2026-09-13_pumpfun-graduation-feasibility.md",),
        reopens_when="A decision to commit to weeks of forward data collection.",
        keywords=("pump.fun", "pumpfun", "graduation", "bonding curve"),
    ),
    Category(
        name="Directional prediction",
        verdict="Closed (as a class)",
        cause="detection_floor",
        reason=(
            "Requires 73.8-94.8% direction accuracy against an achievable mid-50s. "
            "Closed as a CLASS, not as a tally of failures — the bound holds for "
            "strategies nobody has written yet."
        ),
        citations=("planning/decisions/2026-09-14-close-directional-prediction-class.md",),
        reopens_when=(
            "Fixed cost falls materially, size rises materially, or a pair with "
            "noise ratio below 1.33 appears. A new idea within the class is NOT "
            "a reopening condition, and neither is conviction about one."
        ),
        keywords=("predict", "direction", "momentum", "trend", "signal", "forecast",
                  "indicator", "ema", "rsi", "macd", "technical analysis"),
    ),
    Category(
        name="Capital-range increase",
        verdict="Closed",
        cause="detection_floor",
        reason=(
            "Costs were never the binding constraint; the strategy asymptotes at "
            "~22% of buy-and-hold."
        ),
        citations=("planning/decisions/2026-09-13-capital-range-sensitivity.md",),
        reopens_when="A materially different capital scale, which is a different project.",
        keywords=("bigger size", "more capital", "scale up", "increase position"),
    ),
    Category(
        name="DEX market-making / LP",
        verdict="Rejected",
        cause="adverse_selection",
        reason=(
            "Loss-versus-rebalancing — a passive LP is adversely selected by "
            "arbitrageurs and the fee income does not compensate."
        ),
        citations=("planning/decisions/2026-09-14-dex-market-making-lvr.md",),
        reopens_when=(
            "A venue mechanism that removes or rebates LVR (oracle pricing, "
            "batch auctions), or demonstrated uninformed flow exceeding LVR."
        ),
        keywords=("market making", "market-making", "liquidity provision", "lp",
                  "provide liquidity", "amm", "pool fees"),
    ),
    Category(
        name="Funding-rate carry / basis",
        verdict="On hold",
        cause=None,  # closed by scope, not by one of the four causes
        reason=(
            "Requires a perps venue (not Solana spot) and a $100-500 minimum — "
            "outside both the current scope and the $5-$10 size. THE ONLY row "
            "closed by scope and capital rather than by an impossibility."
        ),
        citations=("planning/decisions/2026-09-14-funding-rate-carry.md",),
        reopens_when=(
            "A perps venue plus $100-500 of risk capital per leg. Note the "
            "record flags an unresolved ambiguity: whether that minimum is per "
            "leg or total, which is the difference between $100 and $1,000."
        ),
        keywords=("funding", "carry", "basis", "perp", "perpetual", "delta neutral",
                  "delta-neutral"),
    ),
)

# Candidates disposed of by the four causes without needing their own row.
ALSO_CLOSED: dict[str, str] = {
    "Liquidation hunting": "latency",
    "Stablecoin depeg arbitrage": "latency",
    "CEX-DEX listing arbitrage": "latency",
    "Statistical arbitrage on correlated pairs": "detection_floor",
    "Routing/fee-tier arbitrage inside Jupiter": "latency",
    "MEV / sandwiching": "latency",
}


def validate_citations() -> list[tuple[str, str]]:
    """Return (category, path) for every citation that does not resolve."""
    broken = []
    for cat in LEDGER:
        for path in cat.citations:
            if not (REPO_ROOT / path).exists():
                broken.append((cat.name, path))
    return broken


def lookup(idea: str) -> dict:
    """Return ledger hints for a proposed idea. NOT a verdict.

    Keyword overlap is a prompt to go read the row, nothing more. An idea that
    matches nothing has not been cleared — it has merely failed to trip a
    string match, which is not evidence of novelty.
    """
    text = (idea or "").lower()
    hits = [
        cat for cat in LEDGER
        if any(k in text for k in cat.keywords)
    ]
    also = [
        name for name, cause in ALSO_CLOSED.items()
        if any(w in text for w in name.lower().split() if len(w) > 4)
    ]
    return {
        "idea": idea,
        "keyword_matches": [
            {
                "category": c.name,
                "verdict": c.verdict,
                "cause": CAUSES[c.cause].name if c.cause else "scope and capital (not one of the four causes)",
                "reason": c.reason,
                "citations": list(c.citations),
                "reopens_when": c.reopens_when,
            }
            for c in hits
        ],
        "also_closed_matches": also,
        "is_this_a_verdict": False,
        "what_you_must_still_do": (
            "This is a hint, not a ruling. Per "
            ".claude/skills/structural-edge-inventory: name the category, name "
            "which of the four causes the idea must escape, and say HOW it "
            "escapes. Zero keyword matches does not mean the idea is new — it "
            "means a string match found nothing. If it genuinely escapes all "
            "four, it still passes edge-viability-check before any backtest."
        ),
        "the_four_causes": {k: {"name": v.name, "description": v.description}
                            for k, v in CAUSES.items()},
        "standing_position": (
            "Nothing is left on this ledger at $5-$10 on Solana spot with "
            "retail data access. The binding constraints are position size and "
            "data access, not the code. All three responses the inventory names "
            "(accept the finding, change capital scale, change data access) are "
            "the user's call and none may be built toward unprompted."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--idea", help="Proposed strategy idea to check against the ledger.")
    ap.add_argument("--validate", action="store_true",
                    help="Check that every citation resolves to a real file.")
    args = ap.parse_args()

    if args.validate:
        broken = validate_citations()
        if broken:
            for name, path in broken:
                print(f"BROKEN  {name}: {path}")
            return 1
        print(f"All citations resolve ({sum(len(c.citations) for c in LEDGER)} across {len(LEDGER)} categories).")
        return 0

    if not args.idea:
        for c in LEDGER:
            cause = CAUSES[c.cause].name if c.cause else "scope and capital"
            print(f"{c.verdict:18s} {c.name:34s} {cause}")
        return 0

    print(json.dumps(lookup(args.idea), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
