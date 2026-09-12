"""Measure DexPaprika's usable Solana history depth against GeckoTerminal's.

Single gate condition, fixed before the probe was written:

    How many Solana tokens have >= 180 daily bars on DexPaprika, versus the
    current GeckoTerminal universe (6 tokens with >= 142 daily bars, of which
    5 cleared the >= 120-bar rule in the 2026-09-12 cross-sectional record)?

This exists because the cross-sectional momentum test was capped at five names
by **history depth, not liquidity** — the decision record calls that limitation
load-bearing. A data source with deeper daily history would widen a universe
that is currently too thin to test cross-sectional strategies at all. That is
the only claim being tested here.

Explicitly NOT in scope: replacing GeckoTerminal, feeding the strategy, the
risk engine, or paper mode. `planning/specs/mvp_spec.md` fixes GeckoTerminal as
the OHLC source and this probe does not reopen it. Nothing here imports from
`src/execution/` or writes into the candle cache.

Offline-first: responses are cached under `research/.dexpaprika-probe/`. A
re-run reads the cache and makes no network calls, so the measurement is
reproducible and re-reading it costs nothing.

Run:  .venv/bin/python research/dexpaprika_probe.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

# The gate, fixed before running.
TARGET_BARS = 180
# What GeckoTerminal gave us, from planning/decisions/2026-09-12-...-protocol.md
GECKO_TOKENS_AT_142 = 6
GECKO_TOKENS_KEPT = 5

BASE = "https://api.dexpaprika.com"
NETWORK = "solana"
HEADERS = {"User-Agent": "tradecc/0.1 (history-depth probe)", "Accept": "application/json"}
CACHE = Path("research/.dexpaprika-probe")
POOL_LIMIT = 60
INTERVAL = "24h"
# Liquidity, not volume. The 2026-09-12 record established that volume-ranked
# "top pools" select for micro-liquidity names — and DexPaprika's own listing
# confirms it: its top volume pool reports $0.0005 of liquidity against $117M
# of 24h volume. Ranking by liquidity_usd is the same filter our own universe
# rule uses, which is what makes the comparison like-for-like.
ORDER_BY = "liquidity_usd"
MIN_LIQUIDITY_USD = 250_000
PAUSE_S = 2.2  # keyless tier is 15 req/min; stay well under.


def _get(path: str, cache_key: str) -> dict | None:
    """GET with an on-disk cache. Returns None on any failure, never raises."""
    cached = CACHE / f"{cache_key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    request = urllib.request.Request(f"{BASE}{path}", headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as handle:
            payload = json.loads(handle.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"  request failed ({path}): {exc}")
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(payload))
    time.sleep(PAUSE_S)
    return payload


def top_pools() -> list[dict]:
    """Deepest pools on the network, by USD liquidity.

    Note the endpoint: the vendor spec shipped with this evaluation lists
    `/networks/{network}/pools`, which now returns HTTP 410 "endpoint removed"
    and names `/pools/search` as its replacement. The spec is stale.
    """
    payload = _get(
        f"/networks/{NETWORK}/pools/search"
        f"?limit={POOL_LIMIT}&order_by={ORDER_BY}&sort=desc",
        "pools-by-liquidity",
    )
    if not payload:
        return []
    return payload.get("results") or []


def bar_count(pool_id: str, key: str) -> int | None:
    """Daily bars available for one pool. None if the endpoint gave nothing."""
    payload = _get(
        f"/networks/{NETWORK}/pools/{pool_id}/ohlcv"
        f"?start=2024-01-01&interval={INTERVAL}&limit=1000",
        f"ohlcv-{key}",
    )
    if payload is None:
        return None
    rows = payload if isinstance(payload, list) else payload.get("data") or []
    return len(rows)


def base_symbol(pool: dict) -> str:
    """Non-SOL, non-stable side of the pair, falling back to the pool id."""
    quotes = {"So11111111111111111111111111111111111111112"}
    ids = [t.get("id", "") for t in pool.get("tokens") or []]
    for token_id in ids:
        if token_id and token_id not in quotes:
            return token_id
    return (ids[0] if ids else pool.get("id", ""))[:12]


def main() -> int:
    print("DEXPAPRIKA HISTORY-DEPTH PROBE")
    print(f"Gate: how many Solana tokens have >= {TARGET_BARS} daily bars?")
    print(
        f"Baseline (GeckoTerminal, 2026-09-12): {GECKO_TOKENS_AT_142} tokens with "
        f">= 142 daily bars, {GECKO_TOKENS_KEPT} kept by the >= 120-bar rule.\n"
    )

    pools = top_pools()
    if not pools:
        print("No pool listing returned. Nothing measured — this is NOT evidence")
        print("either way about history depth. Re-run when the API is reachable.")
        return 1

    print(f"{len(pools)} pools listed. Measuring daily-bar depth per pool.\n")
    seen: dict[str, int] = {}
    for pool in pools:
        pool_id = pool.get("id") or ""
        liquidity = float(pool.get("liquidity_usd") or 0)
        if not pool_id or liquidity < MIN_LIQUIDITY_USD:
            continue
        base = base_symbol(pool)
        if base in seen:  # deepest pool per token wins; the list is sorted
            continue
        bars = bar_count(pool_id, pool_id[:16])
        if bars is None:
            continue
        seen[base] = bars
        print(f"  {base[:12]:<12} {bars:>4} daily bars   ${liquidity:>14,.0f}")

    if not seen:
        print("\nNo OHLCV measured. Nothing concluded.")
        return 1

    at_target = sorted(s for s, n in seen.items() if n >= TARGET_BARS)
    at_142 = sorted(s for s, n in seen.items() if n >= 142)

    print(f"\n{'=' * 60}")
    print(f"tokens measured:                 {len(seen)}")
    print(f"tokens with >= {TARGET_BARS} daily bars:  {len(at_target)}  {at_target}")
    print(f"tokens with >= 142 daily bars:   {len(at_142)}")
    print(f"GeckoTerminal at >= 142:         {GECKO_TOKENS_AT_142}")
    print("=" * 60)
    verdict = (
        "MEANINGFULLY LARGER — open a decision record"
        if len(at_142) > GECKO_TOKENS_AT_142 * 2
        else "NOT meaningfully larger — record REJECTED with these numbers"
    )
    print(f"Verdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
