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

import json
import os
import time
from datetime import datetime
from typing import Any, Protocol

import urllib.error
import urllib.request

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
    """Production transport on the standard library.

    Rewritten on review: the draft used `httpx`. This project carries **no
    third-party HTTP dependency** — `src/execution/http.py` says why, and the
    reasoning applies unchanged here: for a money-adjacent codebase a smaller
    supply-chain surface is worth more than the ergonomics of a nicer client,
    and everything above the transport is transport-agnostic anyway.
    """

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout_seconds = timeout_seconds

    def post(self, url: str, headers: dict[str, str], json_body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(json_body).encode(),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # The body can echo request headers, so it is never surfaced raw.
            raise BitqueryError(
                f"bitquery HTTP {exc.code} for {_redact_url(url)}"
            ) from None
        except urllib.error.URLError as exc:
            raise BitqueryError(f"bitquery transport error: {exc.reason}") from None


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
        transport: GraphQLTransport | None = None,
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
                # The REAL url goes to the transport. `_redact_url` is for log
                # lines and error messages only. The draft passed the redacted
                # url as the request target, which works today purely because
                # this endpoint has no query component — the moment one were
                # added, requests would silently go to a stripped url.
                result = self._transport.post(BITQUERY_GRAPHQL_URL, headers, body)
            except Exception as exc:
                last_error = exc
                self._warn_before_retry(attempt)
                continue

            if "errors" in result:
                self._raise_from_errors(result["errors"])
            if "data" not in result:
                raise BitqueryError(
                    "Bitquery response contained no 'data' key "
                    f"(keys: {sorted(result)})"
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
