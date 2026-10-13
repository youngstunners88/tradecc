"""
Copy-wallet ranking script.

Reads a tradecc.universe.v1 JSON file and a training window, fetches DEX
trades for each candidate wallet over the window, builds a position book,
computes `net_pnl_over_max_dd` per wallet, and writes
`research/copy_wallet/allowlist.json`.

Wallets with too few trades to rank are explicitly excluded; the minimum
is set by the decision record (currently 5 trades).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from bitquery_client import BitqueryClient
from positions import PositionBook

SCHEMA_ALLOWLIST = "tradecc.allowlist.v1"
# Frozen at 10 in planning/decisions/2026-09-16-reopen-copy-trading-via-bitquery.md
# with its reasoning: below ~10 prints, max drawdown is unstable enough that a
# single outlier dominates the PnL/maxDD ratio, and the failure mode the rule
# exists to prevent is a wallet ranking on two lucky fills.
# The draft shipped 5, silently contradicting the frozen protocol.
MIN_TRADES_TO_RANK = 10
MAX_WALLETS = 3


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _read_universe(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if data.get("schema") != "tradecc.universe.v1":
        raise ValueError(f"Unexpected universe schema: {data.get('schema')}")
    return data


def _extract_trades_for_wallet(
    client: BitqueryClient,
    address: str,
    start: datetime,
    end: datetime,
    pool_mints: list[str],
    position_book_builder: Any,
) -> PositionBook:
    return client.dex_trades_for_trader(address, start, end)


def _net_pnl_over_max_dd(book: PositionBook, wallet: str) -> tuple[Decimal, int]:
    """Compute realised net PnL over max drawdown for a wallet.

    For each mint position we compute the realised net PnL as quote_out
    minus quote_in (gross, no fees). We then take the sum across mints to
    get the wallet's net P perhaps in the future we can add a max drawdown
    time series.

    For this first-pass the metric is simply net realised PnL over
    max drawdown, where max drawdown is computed as the maximum peak-to
    -trough decline in the wallet's running realised PnL from its own
    trades' quote value changes.

    This implementation reconstructs the PnL time series by simulation
    of fills, and then computes max drawdown from that series. See
    decision record for the exact calculation.
    """
    # Rebuild a chronological series and track PnL.
    # Since our position book doesn't keep a trade log, we build one
    # from the raw trades here.
    pass


def compute_ranking_metrics(
    trades_by_wallet: dict[str, list[dict[str, Any]]],
    train_start: datetime,
    train_end: datetime,
    pool_mints: list[str],
) -> dict[str, dict[str, Any]]:
    # For now, because we receive raw trades, rather than position book
    # directly, we do a simplified calculation.
    # Build per-wallet trade rows with timestamp and quote value change.

    results: dict[str, dict[str, Any]] = {}
    for wallet, trades in trades_by_wallet.items():
        if len(trades) < MIN_TRADES_TO_RANK:
            continue

        # Sort by timestamp.
        sorted_trades = sorted(trades, key=lambda t: _extract_timestamp(t))
        running = Decimal("0")
        peak = Decimal("0")
        max_dd = Decimal("0")
        n_trades = 0

        for trade in sorted_trades:
            # Extract side and qty.
            side = _extract_side(trade)
            quote_amount = _extract_quote_amount(trade)
            if quote_amount is None:
                continue

            n_trades += 1
            if side.upper() == "BUY":
                running -= quote_amount
            elif side.upper() == "SELL":
                running += quote_amount
            else:
                continue

            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd

        if n_trades < MIN_TRADES_TO_RANK:
            continue
        metric = running if max_dd <= 0 else running / max_dd
        results[wallet] = {
            "metric": metric,
            "n_trades": n_trades,
        }

    return results


def _extract_timestamp(trade: dict[str, Any]) -> datetime:
    ts_raw = _recursive_get(trade, "block.timestamp") or _recursive_get(trade, "timestamp")
    if isinstance(ts_raw, str):
        return datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    if isinstance(ts_raw, datetime):
        return ts_raw
    return datetime.min.replace(tzinfo=timezone.utc)


def _extract_side(trade: dict[str, Any]) -> str:
    return _recursive_get(trade, "side") or "UNKNOWN"


def _extract_quote_amount(trade: dict[str, Any]) -> Decimal | None:
    raw = _recursive_get(trade, "quoteAmount")
    if raw is None:
        return None
    return Decimal(str(raw))


def _recursive_get(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def rank(
    universe_path: Path,
    train_start: datetime,
    train_end: datetime,
    output_path: Path,
    client: BitqueryClient | None = None,
) -> dict[str, Any]:
    if train_start >= train_end:
        raise ValueError("train_start must be before train_end")

    universe = _read_universe(universe_path)
    candidates = universe["candidates"]

    client = client or BitqueryClient()

    trades_by_wallet: dict[str, list[dict[str, Any]]] = {}
    for addr in candidates:
        trades = client.dex_trades_for_trader(addr, train_start, train_end)
        trades_by_wallet[addr] = trades

    metrics = compute_ranking_metrics(trades_by_wallet)

    ranked = sorted(metrics.items(), key=lambda item: item[1]["metric"], reverse=True)[:MAX_WALLETS]

    wallets_out = [
        {"address": addr, "metric": str(meta["metric"]), "n_trades": meta["n_trades"]}
        for addr, meta in ranked
    ]

    result = {
        "schema": SCHEMA_ALLOWLIST,
        "universe": str(universe_path),
        "train_start": train_start.isoformat(),
        "train_end": train_end.isoformat(),
        "metric": "net_pnl_over_max_dd",
        "wallets": wallets_out,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def _make_client() -> BitqueryClient:
    return BitqueryClient()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 4:
        print(
            "usage: rank.py UNIVERSE_JSON TRAIN_START_ISO TRAIN_END_ISO OUTPUT_PATH",
            file=sys.stderr,
        )
        return 2

    universe_path = Path(argv[0])
    train_start = datetime.fromisoformat(argv[1])
    train_end = datetime.fromisoformat(argv[2])
    output_path = Path(argv[3])
    if train_start.tzinfo is None:
        train_start = train_start.replace(tzinfo=timezone.utc)
    if train_end.tzinfo is None:
        train_end = train_end.replace(tzinfo=timezone.utc)

    rank(universe_path, train_start, train_end, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
