#!/usr/bin/env python3
"""MCP server exposing TradeCC's viability gate as callable tools.

Why this server exists, when the repo already has the scripts:

A YouTube walkthrough of "seven AI trading repos" (reviewed in
`planning/architecture/2026-09-19-ai-trading-repo-review.md`) is a fair sample
of how trading tooling is usually pitched — more analysts, more dashboards,
more signal generators. None of that moves the two numbers that actually
decide whether a strategy at $5-$10 can work: the fixed cost per round trip,
and the detection floor.

This project already owns those numbers. What it did not have was a way to
apply them in seconds, from any session or tool, to any incoming claim. That
is what this server is: the cheap arithmetic that should run before anyone
spends a month on a backtest, one tool call away.

The arithmetic is NOT reimplemented here. Every tool delegates to
`research/edge_gate.py`, which delegates to `research/trade_power.py`. One
gate, one implementation — the registry rejected a pasted `validation_gate.py`
for precisely the reason a second copy drifts.

Transport is stdio: this is a local tool over local scripts, no network.

    pip install 'tradecc[mcp]'
    PYTHONPATH=src python research/edge_gate_mcp.py
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field

_HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


_gate = _load("edge_gate")
_inventory = _load("edge_inventory")

mcp = MCPServer("tradecc_mcp")

DEFAULT_SIZE = 10.0


@mcp.tool(
    name="tradecc_check_edge_viability",
    annotations=ToolAnnotations(
        title="Run the TradeCC viability gate on a strategy claim",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def tradecc_check_edge_viability(
    claimed_gross_edge_pct: Annotated[
        float | None,
        Field(description=(
            "The hypothesis's claimed gross edge in PERCENT per round trip, "
            "e.g. 0.5 for 0.5%. Pass null when the hypothesis has not stated a "
            "number — that is a real answer (it fails step 1) and the most "
            "common failure, so do not invent a figure to get past it."
        ), ge=-100.0, le=1000.0),
    ] = None,
    size_usd: Annotated[
        float,
        Field(description="Position size in USD. This project's default is $5-$10.",
              gt=0.0, le=1_000_000.0),
    ] = DEFAULT_SIZE,
    window_days: Annotated[
        int,
        Field(description="Length of the test window in days. The gate window in mvp_spec.md is 30.",
              ge=1, le=3650),
    ] = 30,
    trades_per_day: Annotated[
        float,
        Field(description=(
            "Round trips per day the strategy would take. Default 2.35 is "
            "measured from the SOL/USDC 15m backtest, not assumed."
        ), gt=0.0, le=10_000.0),
    ] = 2.35,
) -> str:
    """Decide whether a strategy hypothesis is worth backtesting at all.

    Run this BEFORE writing a backtest, not after. It is the mandatory first
    gate described in `.claude/skills/edge-viability-check`, and it is cheap:
    an afternoon of arithmetic instead of a month of harness code that cannot
    return a trustworthy answer either way.

    Use it on any claim from any source — a paper, a GitHub repo, a video, an
    LLM analyst agent's "high conviction buy". A claim that cannot state a
    gross edge per round trip fails at step 1, which is the correct outcome
    and the most common one.

    Args:
            - claimed_gross_edge_pct (Optional[float]): Gross % per round
              trip, or null if unstated.
            - size_usd (float): Position size, default 10.
            - window_days (int): Test window length, default 30.
            - trades_per_day (float): Round trips per day, default 2.35.

    Returns:
        str: JSON with this schema:
        {
          "verdict": "PASS" | "FAIL" | "INCOMPLETE",
          "claimed_gross_edge_pct": float | null,
          "size_usd": float,
          "break_even_pct": float,      # edge below which it loses by construction
          "trades_needed": float | null, # round trips to separate from zero
          "trades_available": float,     # round trips the window yields
          "window_days": int,
          "steps": [ {"step": int, "name": str,
                      "passed": true|false|null, "detail": str} ],
          "summary": str
        }

        "INCOMPLETE" means steps 1-3 passed and step 4 (does the return
        distribution actually contain this edge) still needs
        research/edge_budget.py against real bars. INCOMPLETE is not a pass.

        A PASS is never evidence an edge exists — only that the measurement
        could see one if it did.

    Examples:
        - "Is a 0.5% per-trade edge testable at $10?" -> edge 0.5, size 10
        - "This repo claims its agents beat the market" -> claimed_gross_edge_pct
          null, because no per-round-trip number was given. Expect a step-1 FAIL.
        - Don't use to measure realised performance of a completed backtest;
          that is research/backtests/ and the replication rule.
    """
    result = _gate.check(
        claimed_gross_edge_pct=claimed_gross_edge_pct,
        size_usd=Decimal(str(size_usd)),
        window_days=window_days,
        trades_per_day=Decimal(str(trades_per_day)),
    )
    return result.to_json()


@mcp.tool(
    name="tradecc_break_even_edge",
    annotations=ToolAnnotations(
        title="Gross edge below which a trade loses money by construction",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def tradecc_break_even_edge(
    size_usd: Annotated[
        float, Field(description="Position size in USD.", gt=0.0, le=1_000_000.0)
    ] = DEFAULT_SIZE,
    fixed_cost_usd: Annotated[
        float,
        Field(description=(
            "Recurring fixed cost per round trip. Default 0.0127 is measured in "
            "research/calibrate_costs.py and excludes refundable ATA rent, which "
            "is a deposit rather than a fee."
        ), ge=0.0, le=1000.0),
    ] = 0.0127,
) -> str:
    """Compute the break-even gross edge for a position size.

    Fixed cost per round trip does not scale down, so the smaller the
    position, the larger the edge has to be just to break even. At $5 the
    hurdle is roughly twice what it is at $10. This is the single number that
    most often kills a small-size strategy before any data is involved.

    Args:
            - size_usd (float): Position size, default 10.
            - fixed_cost_usd (float): Recurring cost per round trip, default 0.0127.

    Returns:
        str: JSON with schema:
        {
          "size_usd": float,
          "fixed_cost_usd": float,
          "break_even_gross_pct": float,  # e.g. 0.254 means 0.254%
          "note": str
        }

    Examples:
        - "What edge do I need at $5?" -> size_usd 5 -> 0.254%
        - Don't use when you also need the sample-size answer; use
          tradecc_check_edge_viability, which includes this.
    """
    import json

    power = _gate.Power(
        size_usd=Decimal(str(size_usd)),
        fixed_cost_usd=Decimal(str(fixed_cost_usd)),
        return_stdev_frac=_gate.DEFAULT_RETURN_STDEV_FRAC,
    )
    be = power.break_even_edge
    return json.dumps(
        {
            "size_usd": size_usd,
            "fixed_cost_usd": fixed_cost_usd,
            "break_even_gross_pct": float(be * 100),
            "note": (
                "Gross edge per round trip below this loses money by "
                "construction. No sample size fixes a negative expectancy."
            ),
        },
        indent=2,
    )


@mcp.tool(
    name="tradecc_minimum_detectable_edge",
    annotations=ToolAnnotations(
        title="Smallest edge a given number of trades could confirm",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def tradecc_minimum_detectable_edge(
    budget_trades: Annotated[
        int,
        Field(description="Round trips the run will actually collect.", ge=1, le=1_000_000),
    ],
    size_usd: Annotated[
        float, Field(description="Position size in USD.", gt=0.0, le=1_000_000.0)
    ] = DEFAULT_SIZE,
) -> str:
    """Compute the smallest gross edge a run of N round trips could confirm.

    The inverse question to sample size: given the trades you will actually
    collect, what is the faintest real edge you could still distinguish from
    luck at 95% confidence and 80% power? Anything fainter than this cannot be
    confirmed by that run no matter what the result looks like.

    Args:
            - budget_trades (int): Round trips the run will collect.
            - size_usd (float): Position size, default 10.

    Returns:
        str: JSON with schema:
        {
          "budget_trades": int,
          "size_usd": float,
          "minimum_detectable_gross_pct": float | null,
          "replication_min_pooled_trades": int,
          "note": str
        }

        minimum_detectable_gross_pct is null when no edge is detectable in
        that many trades.

    Examples:
        - "We'll get ~20 trades. What could that prove?" -> budget_trades 20
        - Use to sanity-check a proposed test window before building it.
    """
    import json

    power = _gate.Power(
        size_usd=Decimal(str(size_usd)),
        fixed_cost_usd=_gate.DEFAULT_FIXED_COST_USD,
        return_stdev_frac=_gate.DEFAULT_RETURN_STDEV_FRAC,
    )
    mde = power.minimum_detectable_edge(budget_trades)
    return json.dumps(
        {
            "budget_trades": budget_trades,
            "size_usd": size_usd,
            "minimum_detectable_gross_pct": float(mde * 100) if mde is not None else None,
            "replication_min_pooled_trades": _gate.REPLICATION_MIN_POOLED_TRADES,
            "note": (
                "A result that 'replicates' on fewer pooled trades than "
                f"{_gate.REPLICATION_MIN_POOLED_TRADES} has not been detected "
                "at 95/80 — it has been guessed at."
            ),
        },
        indent=2,
    )


@mcp.tool(
    name="tradecc_check_inventory",
    annotations=ToolAnnotations(
        title="Check a strategy idea against the closed-category ledger",
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def tradecc_check_inventory(
    idea: Annotated[
        str,
        Field(description=(
            "The proposed strategy idea, in plain language. e.g. 'follow "
            "profitable wallets and mirror their trades' or 'delta-neutral "
            "funding carry'."
        ), min_length=1, max_length=2000),
    ],
) -> str:
    """Check a strategy idea against TradeCC's ledger of already-closed categories.

    Run this FIRST, before tradecc_check_edge_viability — CLAUDE.md's routing
    is "structural-edge-inventory first, then edge-viability-check". There is
    no point costing out an edge for a category that was closed months ago for
    a documented reason.

    **This returns hints, not a ruling.** Keyword overlap is a prompt to go
    read the row. Crucially, ZERO matches does not mean the idea is new — it
    means a string match found nothing, which is not evidence of novelty. The
    judgement the skill requires stays with a human: name the category, name
    which of the four causes the idea must escape, and say HOW it escapes.

    Args:
            - idea (str): The proposed strategy, in plain language.

    Returns:
        str: JSON with schema:
        {
          "idea": str,
          "keyword_matches": [ {"category": str, "verdict": str, "cause": str,
                                "reason": str, "citations": [str],
                                "reopens_when": str} ],
          "also_closed_matches": [str],
          "is_this_a_verdict": false,     # always false, by design
          "what_you_must_still_do": str,
          "the_four_causes": {key: {"name": str, "description": str}},
          "standing_position": str
        }

    Examples:
        - "Should we try copy-trading?" -> matches Copy-trading (Blocked, data
          infrastructure), with the reopening condition and the live PR #14 note.
        - "What about an idea nobody has tried?" -> expect zero matches, and
          read what_you_must_still_do rather than treating that as a green light.
    """
    import json

    return json.dumps(_inventory.lookup(idea), indent=2)


if __name__ == "__main__":
    mcp.run()
