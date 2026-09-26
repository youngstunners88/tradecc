"""
Universe extractor for copy-wallet research.

Reads candidate wallet addresses from Bitquery pool DEX trades within a
selection window, filters out known program IDs, and emits the
`tradecc.universe.v1` JSON schema.

This script must NOT rank candidates. Ranking lives in `rank.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bitquery_client import BitqueryClient

# Known Solana program IDs that appear as trader accounts in DEX trade
# prints but are not control of a private key's token flows.
# This list is intentionally conservative and *not* a performance filter.
# We never exclude an address because it was unprofitable; only because
# the owner cannot actually trade.
KNOWN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # token program
    "11111111111111111111111111111111",  # system program
    "computeBudget111111111111111111111111111111111111111111111111",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",  # ATA program
}

SCHEMA = "tradecc.universe.v1"


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _extract_trader_address(trade: dict[str, Any]) -> str | None:
    """Extract the trader address from a Bitquery trade record.

    This is an inferred field mapping. Must be checked against current
    Bitquery schema before first live run.
    """
    # Try the most common shapes.
    account = trade.get("account")
    if isinstance(account, dict):
        trader = account.get("trader")
        if isinstance(trader, str) and trader:
            return trader

    # Fall back to a flat 'trader' or 'sender' field.
    for key in ("trader", "sender", "txSender", "account_trader"):
        if key in trade and isinstance(trade[key], str) and trade[key]:
            return trade[key]

    return None


def _extract_trade_timestamp(trade: dict[str, Any]) -> datetime | None:
    """Read a trade's timestamp, or None when it cannot be read.

    Returns None rather than a sentinel date on purpose: the caller drops
    what it cannot place in time, and a sentinel of `datetime.min` would
    quietly compare as "before the window" while a sentinel of `datetime.max`
    would quietly compare as "after" — either way an unreadable record would
    be silently classified instead of visibly skipped.
    """
    for path in (("block", "timestamp"), ("blockTime", "timestamp")):
        node: Any = trade
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, str) and node:
            try:
                return datetime.fromisoformat(node.replace("Z", "+00:00"))
            except ValueError:
                return None
        if isinstance(node, datetime):
            return node

    flat = trade.get("timestamp")
    if isinstance(flat, datetime):
        return flat
    if isinstance(flat, str) and flat:
        try:
            return datetime.fromisoformat(flat.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def extract_universe(
    pool_addresses: list[str],
    selection_start: datetime,
    selection_end: datetime,
    client: BitqueryClient | None = None,
) -> dict[str, Any]:
    if not isinstance(pool_addresses, list) or not pool_addresses:
        raise ValueError("pool_addresses must be a non-empty list")
    if selection_start >= selection_end:
        raise ValueError("selection_start must be before selection_end")

    client = client or BitqueryClient()

    candidate_set: set[str] = set()
    for pool in pool_addresses:
        trades = client.dex_trades_for_pool(pool, selection_start, selection_end)
        for trade in trades:
            # The window is re-enforced HERE, locally, and not merely asked
            # for in the query. Added on review: the draft passed the window
            # to Bitquery and trusted the response, which makes the single
            # discipline this whole method rests on — "addresses first seen
            # after selection_end are dropped" — contingent on a remote
            # filter, an inferred field name, and pagination not
            # overshooting. Any of those failing silently readmits exactly
            # the look-ahead the selection window exists to exclude.
            #
            # A trade whose timestamp cannot be read is dropped, not kept.
            # An unreadable timestamp cannot be shown to fall inside the
            # window, and "unknown" must never resolve to "include" here.
            timestamp = _extract_trade_timestamp(trade)
            if timestamp is None or not (selection_start <= timestamp <= selection_end):
                continue
            addr = _extract_trader_address(trade)
            if addr is not None and addr not in KNOWN_PROGRAMS:
                candidate_set.add(addr)

    return {
        "schema": SCHEMA,
        "selection_window_start": _iso_utc(selection_start),
        "selection_window_end": _iso_utc(selection_end),
        "pools": list(pool_addresses),
        "chain": "solana",
        "source": "bitquery",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "extractor_commit": _git_sha(),
        "filters": ["performance_blind only"],
        "candidates": sorted(candidate_set),
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 4:
        print(
            "usage: extract_universe.py OUTPUT_PATH POOL_ADDR_CSV START_ISO END_ISO",
            file=sys.stderr,
        )
        return 2

    output_path = Path(argv[0])
    pools = [p.strip() for p in argv[1].split(",") if p.strip()]
    start = datetime.fromisoformat(argv[2])
    end = datetime.fromisoformat(argv[3])
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    universe = extract_universe(pools, start, end)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(universe, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
