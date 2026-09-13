"""Helius JSON-RPC client — read-only.

Stage 2 exposes health, balance, and blockhash. Nothing here signs or
sends; `sendTransaction` and `simulateTransaction` arrive in Stage 6.

The API key travels in the URL query string, which makes logging the URL
a key leak. Two defences: the key is registered with the log scrubber at
construction, and every request passes a redacted URL for logging so the
real one is never handed to a log call in the first place.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from core.config import ProvidersConfig
from core.logging import get_logger, register_secret
from core.rate_limit import RateLimiter
from execution.http import (
    HttpTransport,
    ProviderError,
    ProviderHttpClient,
    RetryPolicy,
    UrllibTransport,
)

logger = get_logger("tradecc.helius")

PROVIDER = "helius"
LAMPORTS_PER_SOL = Decimal("1000000000")


class HeliusRpcClient:
    def __init__(
        self,
        providers: ProvidersConfig,
        api_key: str,
        transport: HttpTransport | None = None,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Helius API key is required")
        # So the key is scrubbed even if it reaches a log line by accident.
        register_secret(api_key)
        self._url = f"{providers.helius_base_url}/?api-key={api_key}"
        self._redacted_url = f"{providers.helius_base_url}/?api-key=***REDACTED***"
        self._http = ProviderHttpClient(
            provider=PROVIDER,
            transport=transport or UrllibTransport(),
            limiter=limiter
            or RateLimiter(
                max_requests=providers.helius_max_requests_per_minute,
                per_seconds=60.0,
                name=PROVIDER,
            ),
            retry=retry,
        )
        self._request_id = 0

    def _rpc(self, method: str, params: list[Any] | None = None) -> Any:
        self._request_id += 1
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params or [],
            }
        ).encode()

        payload = self._http.request(
            "POST",
            self._url,
            headers={"Content-Type": "application/json"},
            body=body,
            redacted_url=self._redacted_url,
        ).json()

        if not isinstance(payload, dict):
            raise ProviderError(PROVIDER, f"{method}: response was not a JSON object")
        if "error" in payload:
            error = payload["error"]
            message = error.get("message", error) if isinstance(error, dict) else error
            raise ProviderError(PROVIDER, f"{method}: {message}")
        if "result" not in payload:
            raise ProviderError(PROVIDER, f"{method}: response had no result")
        return payload["result"]

    def get_health(self) -> str:
        """`getHealth` returns the string "ok" on a healthy node."""
        result = self._rpc("getHealth")
        return str(result)

    def get_balance_lamports(self, pubkey: str) -> int:
        result = self._rpc("getBalance", [pubkey])
        if not isinstance(result, dict) or "value" not in result:
            raise ProviderError(PROVIDER, "getBalance: response had no value")
        try:
            return int(result["value"])
        except (TypeError, ValueError) as exc:
            raise ProviderError(PROVIDER, "getBalance: value was not an integer") from exc

    def get_balance_sol(self, pubkey: str) -> Decimal:
        return Decimal(self.get_balance_lamports(pubkey)) / LAMPORTS_PER_SOL

    def get_latest_blockhash(self) -> str:
        result = self._rpc("getLatestBlockhash", [{"commitment": "confirmed"}])
        try:
            return str(result["value"]["blockhash"])
        except (TypeError, KeyError) as exc:
            raise ProviderError(
                PROVIDER, "getLatestBlockhash: response had no blockhash"
            ) from exc
