"""Resolve and cache the cross-sectional momentum universe.

Implements the universe rule fixed in
`planning/decisions/2026-09-12-cross-sectional-momentum-protocol.md`
literally: USDC-quoted pools, deepest pool per base token, >= 120 daily
bars of history, >= $250k reserves.

Pool *discovery* uses GeckoTerminal's pool listing directly (it is a
catalogue lookup, not price data). Price data goes through the real
`GeckoTerminalClient` and `CandleCache`, so the bars feeding the backtest
come through the same tested, rate-limited, UA-correct path as every
other series in this project.

The resolved universe is written to disk so a run is reproducible and
the backtest never re-resolves (which could silently drift as pool
rankings change).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_config  # noqa: E402
from execution.candle_cache import CandleCache  # noqa: E402
from execution.geckoterminal import GeckoTerminalClient  # noqa: E402

# Fixed in the decision record.
MIN_DAILY_BARS = 120
MIN_RESERVES_USD = 250_000
QUOTE_SYMBOL = "USDC"
PAGES = 5
INTERVAL = "1d"

LISTING = "https://api.geckoterminal.com/api/v2/networks/solana/pools?page={}"
HEADERS = {"User-Agent": "tradecc/0.1", "Accept": "application/json"}
UNIVERSE_FILE = Path("research/.universe.json")


def _listing(page: int) -> dict:
    request = urllib.request.Request(LISTING.format(page), headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as handle:
        return json.loads(handle.read().decode())


def discover() -> dict[str, dict]:
    """Deepest USDC-quoted pool per base token, above the reserve floor."""
    best: dict[str, dict] = {}
    for page in range(1, PAGES + 1):
        for pool in _listing(page).get("data", []):
            attrs = pool["attributes"]
            name = attrs.get("name") or ""
            if "/" not in name:
                continue
            base, _, quote = name.partition("/")
            base, quote = base.strip(), quote.strip()
            # Quote symbol can carry a fee tier suffix ("USDC 0.05%").
            if not quote.upper().startswith(QUOTE_SYMBOL):
                continue
            reserves = float(attrs.get("reserve_in_usd") or 0)
            if reserves < MIN_RESERVES_USD:
                continue
            if base not in best or reserves > best[base]["reserves_usd"]:
                best[base] = {
                    "symbol": base,
                    "pool": pool["id"].replace("solana_", ""),
                    "reserves_usd": reserves,
                    "name": name,
                }
        time.sleep(2.2)
    return best


def main() -> int:
    config = load_config("config.backtest.yaml", env={})
    cache = CandleCache(config.data.cache_dir)
    client = GeckoTerminalClient(config.data)

    print("Resolving universe per the 2026-09-12 decision record")
    print(f"  rule: {QUOTE_SYMBOL}-quoted, deepest pool per token, "
          f">= {MIN_DAILY_BARS} daily bars, >= ${MIN_RESERVES_USD:,} reserves\n")

    candidates = discover()
    print(f"{len(candidates)} {QUOTE_SYMBOL}-quoted candidates above the reserve floor\n")

    resolved = []
    for entry in sorted(candidates.values(), key=lambda e: -e["reserves_usd"]):
        try:
            candles = cache.load_or_fetch(
                entry["pool"],
                INTERVAL,
                lambda: client.fetch_candles(entry["pool"], INTERVAL, limit=1000),
            )
        except Exception as exc:  # noqa: BLE001 - a discovery step, report and skip
            print(f"  {entry['symbol']:10} FETCH FAILED  {exc}")
            continue
        bars = len(candles)
        keep = bars >= MIN_DAILY_BARS
        print(
            f"  {entry['symbol']:10} {bars:>4} bars  "
            f"${entry['reserves_usd']:>12,.0f}  "
            f"{'KEEP' if keep else 'drop (history)'}"
        )
        if keep:
            resolved.append(
                {**entry, "bars": bars, "first": candles[0].timestamp.isoformat()}
            )
        time.sleep(2.2)

    UNIVERSE_FILE.write_text(json.dumps(resolved, indent=2))
    print(f"\nresolved universe: {[e['symbol'] for e in resolved]}")
    print(f"written to {UNIVERSE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
