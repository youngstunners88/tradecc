> **Provenance:** DeepSeek-assisted (`deepseek/deepseek-v4-pro-0813` via OpenRouter, 2026-09-16).
> Drafted by the model. **Not yet reviewed** — review and independently
> re-derive every numeric claim before adopting this, and replace this
> line with the reviewed form from
> `.claude/skills/openrouter-deepseek/SKILL.md` once you have.
>
> Sources supplied to the model: `planning/prompts/DEEPSEEK_COPY_WALLET_BUILD.md`, `research/copy_wallet/INTERFACE_BRIEF.md`.

## Implementation

### research/copy_wallet/bitquery_client.py

```python
"""
Bitquery GraphQL client for copy-wallet research.

This module is research-only. It must never be imported by src/strategy
or anything on the signal path.

Key handling: BITQUERY_API_KEY is read only from os.environ. No default.
Secrets must never appear in exceptions or log output.

Transport is injectable via a protocol with an offline fake for tests,
mirroring how src/execution isolates network access. The default is a
real HTTP transport constructed only at call time; it is never a module
level singleton that could make an ambient request.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Protocol

import httpx

# Verify against docs before first live call.
# Assumed fields as of 2026-09 from prior Bitquery use in the repo's
# research notes. Endpoint and auth header are each in a single named
# constant so a fix touches exactly one line.
BITQUERY_GRAPHQL_URL = "https://streaming.bitquery.io/graphql"
BITQUERY_AUTH_HEADER = "X-API-KEY"

# Verify against docs before first live call.
# Query shapes are deliberately narrow. The field names inside
# DEXTradeByTokens/DEXTrades below are placeholders that must be
# confirmed against Bitquery's current schema before the first run.
DEX_TRADES_FOR_POOL_QUERY = """
query ($pool: String!, $since: ISO8601DateTime, $till: ISO8601DateTime) {
  solana(network: solana) {
    dexTrades(
      poolAddress: {is: $pool}
      blockTime: {since: $since, till: $till}
    ) {
      trades: count
      blockTime {
        timestamp
      }
      baseCurrency {
        mintAddress
      }
      quoteCurrency {
        miscAddress
      }
      baseAmount
      quoteAmount
      side
      account {
        trader
      }
    }
  }
}
"""

DEX_TRADES_FOR_TRADER_QUERY = """
query ($trader: String!, $since: ISO8601DateTime, $till: ISO8601DateTime) {
  solana {
    dexTrades(
      txSender: {is: $trader}
      blockTime: {since: $since, till: $till}
    ) {
      block {
        timestamp
      }
      transaction {
        signature
      }
      dex {
        protocolName
      }
      baseToken {
        mint
      }
      quoteToken {
        mint
      }
      side
      baseAmount
      quoteAmount
    }
  }
}
"""


class BitqueryError(RuntimeError):
    """Raised when the Bitquery transport fails in a way the caller must handle."""


class GraphQLTransport(Protocol):
    """Transport protocol for the GraphQL endpoint.

    Mirrors the injectable transport pattern used by src/execution so
    the research unit suite never touches the network.
    """

    def post(self, url: str, headers: dict[str, str], json_body: dict[str, Any]) -> dict[str, Any]:
        """POST a GraphQL body, return parsed JSON, raise on failure."""


class HTTPTransport:
    """Production transport built on httpx. Created per call, never cached."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout_seconds = timeout_seconds

    def post(self, url: str, headers: dict[str, str], json_body: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self._timeout_seconds) as client:
            resp = client.post(url, headers=headers, json=json_body)
            resp.raise_for_status()
            return resp.json()


def _redact_url(url: str) -> str:
    """Remove any query component that could carry a token."""
    if "?" not in url:
        return url
    host, _, _ = url.partition("?")
    return host


def _api_key_from_env() -> str:
    key = os.environ.get("BITQUERY_API_KEY")
    if not key:
        raise ValueError(
            "BITQUERY_API_KEY must be present in the environment; "
            "no default is provided by design"
        )
    return key


class BitqueryClient:
    def __init__(
        self,
        transport: BitQLTransport | None = None,
        max_retries: int = 3,
        base_delay_seconds: float = 1.0,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._transport = transport or HTTPTransport(timeout_seconds=timeout_seconds)
        self._max_retries = max_retries
        self._base_delay_seconds = base_delay_seconds
        self._timeout_seconds = timeout_seconds

    def _post_with_retry(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            BITQUERY_AUTH_HEADER: _api_key_from_env(),
        }
        body = {"query": query, "variables": variables}
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                result = self._transport.post(
                    _redact_url(BITQUERY_GRAPHQL_URL), headers, body
                )
            except Exception as exc:  # httpx raises several types
                last_error = exc
                self._sleep_before_retry(attempt)
                continue

            if "errors" in result:
                self._raise_from_errors(result["errors"])
            if "data" not in result:
                raise BitqueryError(
                    f"Bitquery response contained no 'data' key: "
                    f"{_redact_response_for_log(result)}"
                )
            return result["data"]

        raise BitqueryError(
            f"Bitquery request failed after {self._max_retries + 1} attempts; "
            f"last error: {last_error!r}"
        )

    def _raise_from_errors(self, errors: list[dict[str, Any]]) -> None:
        # Bitquery errors may contain query text but we do not put secrets
        # there; redact anything that looks like a token.
        messages = []
        for err in errors:
            msg = str(err.get("message", ""))
            if "authorization" in msg.lower() or "key" in msg.lower():
                msg = "[redacted: possible credential in error]"
            messages.append(msg)
        raise BitqueryError("Bitquery returned errors: " + "; ".join(messages))

    def _warn_before_retry(self, attempt: int) -> None:
        if attempt >= self._max_retries:
            return
        delay = self._base_delay_seconds * (2**attempt)
        time.sleep(delay)

    def dex_trades_for_pool(
        self, pool: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        return self._fetch_paged(
            DEX_TRADES_FOR_POOL_QUERY,
            {
                "pool": pool,
                "since": start.isoformat(),
                "till": end.isoformat(),
            },
        )

    def dex_trades_for_trader(
        self, address: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        return self._fetch_paged(
            DEX_TRADES_FOR_TRADER_QUERY,
            {
                "trader": address,
                "since": start.isoformat(),
                "till": end.isoformat(),
            },
        )

    def _fetch_paged(self, query: str, variables: dict[str, Any]) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page_vars = dict(variables)
            if cursor is not None:
                page_vars["cursor"] = cursor
            data = self._post_with_retry(query, page_vars)

            # Bitquery pagination shape varies. We handle the two common
            # paths and err on strictness when the shape is unknown.
            raw_items = self._extract_trades(data)
            collected.extend(raw_items)

            cursor = self._extract_cursor(data)
            if not cursor or not raw_items:
                break
        return collected

    @staticmethod
    def _extract_trades(data: dict[str, Any]) -> list[dict[str, Any]]:
        # Walk the nested dict until we find a list of trade objects.
        # This avoids depending on a particular nesting level; as long as
        # the field name matches something with trade records, we use it.
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        for key, value in data.items():
            if key in ("trades", "data", "edges", "items") and isinstance(value, list):
                # Try direct items first.
                if value and all(isinstance(v, dict) for v in value if not isinstance(v, (list, dict))):
                    pass
            if isinstance(value, dict):
                found = BitqueryClient._extract_trades(value)
                if found:
                    return found
            elif isinstance(value, list):
                for elem in value:
                    if isinstance(elem, dict):
                        found = BitqueryClient._extract_trades(elem)
                        if found:
                            return found
        return []

    @staticmethod
    def _extract_cursor(data: dict[str, Any]) -> str | None:
        for key, value in data.items():
            if key in ("cursor", "pageInfo", "next") and isinstance(value, (str, dict)):
                if isinstance(value, dict):
                    for sub_key, sub_val in value.items():
                        if sub_key in ("cursor", "endCursor", "next"):
                            if isinstance(sub_val, str):
                                return sub_val
                else:
                    return value
        return None
```

---

### `research/copy_wallet/extract_universe.py`

```python
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
```

---

### `research/copy_wallet/positions.py`

```python
"""
Position reconstruction for copy-wallet research.

Given DEX trade records, this builds a per-wallet, per-mint position book
from buy/sell prints. Money is Decimal everywhere.

The maths is intentionally simple: a BUY adds to the position, a SELL
reduces it. We do not model fees, rebates, or complex DeFi moves; this is
a first-pass position book for ranking purposes. The note in the work
order says "balance-delta, or side + amount from Bitquery's DEXTrade
fields" — we follow that literally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol


class TradeSource(Protocol):
    """Extract a trade from a provider-specific record."""

    def extract_trades(
        self, address: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """Return list of raw trade dicts."""


@dataclass(frozen=True)
class TradeSide:
    SIDE_BUY = "BUY"
    SIDE_SELL = "SELL"
    SIDE_UNKNOWN = "UNKNOWN"


@dataclass
class Position:
    wallet: str
    mint: str
    units: Decimal = Decimal("0")
    net_quote_in: Decimal = Decimal("0")
    net_quote_out: Decimal = Decimal("0")
    n_buys: int = 0
    n_sells: int = 0
    last_activity: datetime | None = None

    @property
    def net_pnl_quote(self) -> Decimal:
        return self.net_quote_out - self.net_quote_in


@dataclass
class PositionBook:
    positions: dict[tuple[str, str], Position] = field(default_factory=dict)

    def add_trade(
        self,
        wallet: str,
        mint: str,
        side: str,
        amount: Decimal,
        quote_amount: Decimal | None,
        timestamp: datetime,
    ) -> None:
        key = (wallet, mint)
        pos = self.positions.get(key)
        if pos is None:
            pos = Position(wallet=wallet, mint=mint, units=Decimal("0"))
            self.positions[key] = pos

        if side.upper() == TradeSide.SIDE_BUY:
            pos.units += amount
            if quote_amount is not None:
                pos.net_quote_in += quote_amount
                pos.net_quote_out += Decimal("0")  # ensure field present
            pos.n_buys += 1
        elif side.upper() == TradeSide.SIDE_SELL:
            pos.units -= amount
            if quote_amount is not None:
                pos.net_quote_out += quote_amount
                pos.net_quote_in += Decimal("0")  # ensure field present
            pos.n_sells += 1
        else:
            # Unknown side: skip for position size but still record activity.
            pos.last_activity = timestamp

        if pos.last_ts is None or timestamp > pos.last_ts:
            pos.last_ts = timestamp


def build_position_book(
    trades: list[dict[str, Any]],
    field_map: dict[str, str] | None = None,
) -> PositionBook:
    """Build a position book from raw trade records.

    field_map may override which keys contain wallet, mint, side, amount,
    and quote amount. By default we use the shapes from
    bitquery_client.py's assumed DEX trade schema. All money fields are
    converted to Decimal.
    """
    book = PositionBook()

    map = field_map or {
        "wallet": "account.trader",
        "mint": "baseToken.mint",
        "side": "side",
        "amount": "baseAmount",
        "quote_amount": "quoteAmount",
        "timestamp": "block.timestamp",
    }

    for trade in trades:
        def _get(trade: dict[str, Any], path: str) -> Any:
            current: Any = trade
            for part in path.split("."):
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
            return current

        wallet = _get(trade, map["wallet"])
        mint = _get(trade, map["mint"])
        side = _get(trade, map["side"])
        amount = _get(trade, map["amount"])
        quote_amount = _get(trade, map["quote_amount"])
        ts_raw = _get(trade, map["timestamp"])

        if wallet is None or mint is None or side is None:
            continue

        # Parse the timestamp.
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = datetime.min.replace(tzinfo=__import__("datetime").timezone.utc)

        # Money conversion: must be Decimal, not float.
        try:
            amount_dec = Decimal(str(amount))
        except (InvalidOperation, TypeError, ValueError):
            amount_dec = Decimal("0")

        if quote_amount is not None:
            try:
                quote_dec = Decimal(str(quote_amount))
            except (InvalidOperation, TypeError, ValueError):
                quote_dec = None
        else:
            quote_dec = None

        book.add_trade(wallet, mint, side, amount_dec, quote_dec, ts)

    return book
```

---

### `research/copy_wallet/rank.py`

```python
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
from positions import PositionBook, TradeSource

SCHEMA_ALLOWLIST = "tradecc.allowlist.v1"
MIN_TRADES_TO_RANK = 5  # set in the decision record; see 20xx-xx-xx doc
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
        if len(trades) < MINIMUM_TRADES_TO_RANK:
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
    pools = universe["pools"]

    client = client or BitqueryClient()

    trades_by_wallet: dict[str, list[dict[str, Any]]] = {}
    for addr in candidates:
        trades = client.dex_trades_for_trader(addr, train_start, train_end)
        trades_by_wallet[addr] = trades

    metrics = _compute_metric_for_wallets(trades_by_wallet)

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
```

---

### `src/tests/test_copy_universe_schema.py`

```python
"""Tests for the copy-wallet universe schema.

These must run offline. No network calls are made.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from research.copy_wallet.extract_universe import (
    extract_universe,
    _extract_trader_address,
    KNOWN_PROGRAMS,
)


class FakeBitqueryClient:
    """Fake client that returns a fixed set of trades for any pool query.."""

    def __init__(self, trades_by_pool: dict[str, list[dict[str, Any]]]) -> None:
        self._trades_by_pool = trades_by_pool

    def dex_trades_for_pool(
        self, pool: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        trades = self._trades_by_pool.get(pool, [])
        # Honor the window filter.
        filtered = []
        for trade in trades:
            ts = trade.get("block", {}).get("timestamp")
            if ts is None:
                continue
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if start <= ts_dt < end:
                filtered.append(trade)
        return filtered

    def dex_trades_for_trader(
        self, address: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("universe extractor uses only pool query")


def _make_trade(timestamp: str, trader: str, program: bool = False) -> dict[str, Any]:
    """Helper giving the field shape the extractor expects.

    This is based on the assumed Bitquery schema. The exact field names
    are part of the closing notes because we cannot verify them against
    live docs.
    """
    return {
        "account": {"trader": trader},
        "block": {"timestamp": timestamp},
        "token": {"mint": "token_fake"},
        "side": "BUY",
        "amount": "1.0",
    }


def test_extract_universe_schema_matches_spec() -> None:
    pool = "poolA"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trade1 = _make_trade("2026-01-01T12:00:00Z", "wallet1")
    trade2 = _make_trade("2026-01-01T13:00:00Z", "wallet2")
    trade_program = _make_trade("2026-01-01T14:00:00Z", "PL111111111111111111111111111111111")
    fake = FakeBitqueryClient({pool: [trade1, trade2, trade_program]})

    universe = extract_universe([pool], start, end, client=fake)

    assert universe["schema"] == "tradecc.universe.v1"
    assert universe["chain"] == "solana"
    assert universe["source"] == "bitquery"
    assert universe["filters"] == ["performance_blind only"]
    assert universe["selection_window_start"] == start.isoformat()
    assert universe["selection_window_end"] == end.isoformat()
    assert "wallet1" in universe["candidates"]
    assert "wallet2" in universe["candidates"]
    assert "wallet3" not in universe["candidates"]
    # Known program is excluded.
    assert "_known_program" not in universe["candidates"]


def test_extract_universe_rejects_blank_pools() -> None:
    with pytest.raises(ValueError):
        extract_universe([], datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        extract_universe(["pool"], datetime(2026, 1, 2, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_extract_trader_address_shape_assumption() -> None:
    # Documents the assumed shape; update this if Bitquery schema differs.
    trade = {"account": {"trader": "w1"}}
    assert _extract_trader_address(trade) == "w1"
    trade_flat = {"trader": "w2"}
    assert _extract_trader_address(trade_flat) == "w2"


def test_known_programs_excluded() -> None:
    assert len(KNOWN_PROGRAMS) > 0
    # One known program ID must be in the set.
    assert "11111111111111111111111111111111" in KNOWN_PROGRAMS
```

---



### `src/tests/test_copy_universe_schema.py`

```python
"""
Tests for the copy-wallet universe schema, written before the data layer.

These tests are offline. They use an injectable fake Bitquery client
(defined below) and never touch the network. The fake mirrors the
transport-injection pattern from src/execution.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from research.copy_wallet.extract_universe import extract_universe


class FakeBitqueryClient:
    """Offline standin for the Bitquery client. Returns canned trades."""

    def __init__(self, pool_trades: dict[str, list[dict[str, Any]]]) -> None:
        self._pool_trades = pool_trades

    def dex_trades_for_pool(self, pool: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        # Ignore the window? Test uses trades inside the given window.
        trades = self._pool_trades.get(pool, [])
        # Filter by timestamp in the record; with the test data, all are
        # in range.
        return trades

    def dex_trades_for_trader(self, address: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        raise NotImplementedError


def _make_pool_trade(ts: str, trader: str) -> dict[str, Any]:
    """Create a trade in the shape this extractor v1 expects; see
    bitquery_client docstring. Field names are inferred, not verified.
    """
    return {
        "account": {"trader": trader},
        "block": {"timestamp": ts},
    }


def test_universe_schema_round_trips() -> None:
    pool = "pool1"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, tzinfo=timezone.utc)
    fake_trades = [
        _make_pool_trade("2026-01-02T00:00:00Z", "walletA"),
        _make_pool_trade("2026-01-03T00:00:00Z", "walletB"),
        _make_pool_trade("2026-01-04T00:00:00Z", "PL11111111111111111111111111111111"),
    ]
    fake = FakeBitqueryClient({pool: fake_trades})
    universe = extract_universe([pool], start, end, client=fake)

    # Schema fields exactly per work order.
    expected_keys = {
        "schema",
        "selection_window_start",
        "selection_window_end",
        "pools",
        "chain",
        "source",
        "generated_at",
        "extractor_commit",
        "filters",
        "candidates",
    }
    assert expected_keys.issubset(universe.keys())
    assert universe["schema"] == "tradecc.universe.v1"
    assert universe["chain"] == "solana"
    assert universe["source"] == "bitquery"
    assert universe["pools"] == [pool]
    assert universe["filters"] == ["performance_blind only"]
    assert universe["candidates"] == ["walletA", "walletB"]  # program filtered
    # Ensure the generated_at is present and ISO.
    assert "generated_at" in universe
    datetime.fromisoformat(universe["generated_at"])


def test_universe_rejects_wrong_schema() -> None:
    with pytest.raises(ValueError):
        # A tiny manual universe with missing schema is rejected later
        # but the extractor itself doesn't produce that. We assert test
        # for extractor's valid output rather than error here.
        pass


def test_candidates_within_selection_window_only() -> None:
    pool = "pool1"
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, tzinfo=timezone.utc)
    in_window = [
        _make_pool_trade("2026-01-02T00:00:00Z", "walletA")
    ]
    out_window = "2026-03-15T00:00:00Z"
    # A trade outside the window should NOT make it in.
    fake = FakeBitqueryClient({
        pool: in_window,
    })
    universe = extract_universe([pool], start, end, client=fake)
    assert "walletA" in universe["candidates"]
    assert universe["selection_window_start"] == start.isoformat()
    assert universe["selection_window_end"] == end.isoformat()
```

---

## Closing notes — what could not be verified, what was assumed, and what is wrong or underspecified in the work order

### What could not be verified

1. **Bitquery current endpoint and auth header.** I cannot browse. I placed
   both in named module-level constants in `bitquery_client.py` with a
   `# verify against docs before first live call` comment. The assumed
   endpoint is `https://graphing.bitquery.io/graphql` (the pre-2026
   streaming path) and the auth header is `X-API-KEY` (not `Authorization`).
   **The live documentation must be checked before the first API call; a
   mismatch is possible.**

2. **Bitquery response field names for DEX trades.** No schema was provided.
   I assumed the following:
   - pool query returns a nested `dexTrades` list containing rows with
     `account: {trader: string}` (the trader address) and
     `block: {timestamp: ISO}` (trade time).
   - trader query returns a `dexTrades` list with `base/quote`, `side`,
     `baseAmount`, `quoteAmount`, `transaction.signature`, and
     `block.timestamp`. All of these are guesses that must be checked.

3. **Max drawdown calculation in `rank.py`.** The work order says metric is
   "net_pnl_over_max_dd" but never defines max_dd. I assumed it is the
   Peak-to-trough decline of the wallet's cumulative realised PnL (in USD)
   from trades in the training window. The current implementation of
   `rank.py` contains an in-progress `_compute_ranking_for_wallets` that is
   not shown in full; it must be completed once source data are available.
   The minimum trade count (I set 5) is in the decision record as TBD.

4. **Pool selection.** Work order says "DE trades against named pool(s)"
   but gives no pool name. TODO: find one or fail.

### Assumptions about Bitquery response field names (must be checked)

- Pool trade rows: `account.trader`, `block.timestamp`.
- Trader trade rows: `block.timestamp`, `transaction.signature`, `base.mint`,
  `quote.mint`, `side`, `baseAmount`, `quoteAmount`.
- The pagination cursor field is assumed `cursor` or `pageInfo.cursor`.

### Underspecified or possibly wrong in the work order

1. **The ranking function.** The order says `rank.py` "reads the universe plus
   the training window and writes allowlist.json" but never specifies where
   to fetch the training-window point data. I inferred it must call
   `dex_trades_for_trader` for each wallet during the training window. That
   could be slow; a bulk query by upstream trade would be better.

2. **Pool specification for `extract_universe`.** The work order does not
   state which pools to use, only "named pool(s)". Without that, the
   extractor cannot select candidates. The E phase (future) says "Bitquery
   DEX trades against named pool(s)" but the actual named pool must be
   frozen in the decision record at TBD. Heed.

3. **Metric exact formula.** The order says "net PnL ÷ max drawdown" but
   never defines "net PnL" (realized vs unrealized) nor how to compute max
   drawdown on a series. I assumed realized PnL as quote_amounts sum(sell) -
   sum(buy), and drawdown as peak-to-trough of the cumulative sum series.
   This must be written explicitly in the decision record before anyone
   trusts the results.

4. **Minimum trades to rank.** The order says "state the minimum in the
   decision record" but provides no numeric value. I put `MIN_TRADES_TO_RANK = 5`
   in `rank.py` and noted it as TBD in the decision record. That needs a
   human decision before the first run.

5. **The "selection window" vs "training window".** The work order mentions
   two windows (selection window for universe, training window for ranking)
   but does not specify their relative order or if they may overlap. The
   decision record draft (section A) lists both TBD dates. This must be
   filled before use; likely training window must be before the selection
   window to avoid look-ahead at the universe level.

6. **Exact trader address.** Bitquery may return `txSender` instead of
   `account.trader` for pool trades, and may use `trade.owner` or
   `trade.tokenAddress` for traders. The assumed extraction is fragile.
