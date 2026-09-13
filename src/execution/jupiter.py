"""Jupiter quote client — quotes only, no transaction building.

Stage 2 reads prices and nothing else. There is no method here that
builds, signs, or sends a swap: live execution is Stage 6, behind the
validation gate.

Targets the free public host by default. Moving to the keyed host is a
config change, never a silent fallback when the free tier throttles — a
fallback that quietly starts spending money is the wrong shape for this.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from core.config import ProvidersConfig
from core.logging import get_logger
from core.rate_limit import RateLimiter
from core.types import Quote, Side
from execution.http import (
    HttpTransport,
    ProviderError,
    ProviderHttpClient,
    RetryPolicy,
    UrllibTransport,
)

logger = get_logger("tradecc.jupiter")

PROVIDER = "jupiter"


@dataclass(frozen=True)
class JupiterQuote:
    """The raw quote alongside the domain object, for auditing and contract tests."""

    quote: Quote
    raw: dict[str, Any]
    # The route's expected price impact for this size, as a percentage.
    # This is the *measured* cost of depth, and it is not the same thing as
    # `worst_case_price`: that reflects the slippage tolerance we asked
    # for, which bounds the downside but is not what a fill is expected to
    # cost. Backtest slippage is calibrated from this — see
    # research/calibrate_costs.py.
    price_impact_pct: Decimal = Decimal("0")


class JupiterQuoteClient:
    def __init__(
        self,
        providers: ProvidersConfig,
        transport: HttpTransport | None = None,
        limiter: RateLimiter | None = None,
        retry: RetryPolicy | None = None,
    ) -> None:
        self._base_url = providers.jupiter_base_url
        self._http = ProviderHttpClient(
            provider=PROVIDER,
            transport=transport or UrllibTransport(),
            limiter=limiter
            or RateLimiter(
                max_requests=providers.jupiter_max_requests_per_minute,
                per_seconds=60.0,
                name=PROVIDER,
            ),
            retry=retry,
        )

    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        slippage_bps: int,
        amount_usd: Decimal,
        side: Side = Side.BUY,
    ) -> Quote:
        return self.get_quote_detailed(
            input_mint, output_mint, amount_atomic, slippage_bps, amount_usd, side
        ).quote

    def get_quote_detailed(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        slippage_bps: int,
        amount_usd: Decimal,
        side: Side = Side.BUY,
    ) -> JupiterQuote:
        if amount_atomic <= 0:
            raise ValueError("amount_atomic must be positive")
        if slippage_bps < 0:
            raise ValueError("slippage_bps must not be negative")

        query = urllib.parse.urlencode(
            {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount_atomic,
                "slippageBps": slippage_bps,
            }
        )
        url = f"{self._base_url}/swap/v1/quote?{query}"
        payload = self._http.request("GET", url).json()
        return self._to_quote(payload, output_mint, amount_usd, side)

    def _to_quote(
        self, payload: Any, output_mint: str, amount_usd: Decimal, side: Side
    ) -> JupiterQuote:
        if not isinstance(payload, dict):
            raise ProviderError(PROVIDER, "quote response was not a JSON object")

        in_amount = _required_int(payload, "inAmount")
        out_amount = _required_int(payload, "outAmount")
        # The minimum the route guarantees at the requested slippage. This is
        # the number the risk engine's slippage cap actually reads.
        threshold = _required_int(payload, "otherAmountThreshold")

        if out_amount <= 0 or threshold <= 0:
            raise ProviderError(PROVIDER, "quote returned a non-positive output amount")

        # Prices are input-per-output ratios in atomic units. Token decimals
        # cancel in the ratio, so slippage_pct is exact without a decimals
        # lookup; USD-denominated pricing arrives with the data layer.
        expected_price = Decimal(in_amount) / Decimal(out_amount)
        worst_case_price = Decimal(in_amount) / Decimal(threshold)

        quote = Quote(
            token_mint=output_mint,
            side=side,
            amount_usd=amount_usd,
            expected_price=expected_price,
            worst_case_price=worst_case_price,
            # Jupiter's quote excludes Solana network, priority, and rent
            # costs. Those are modelled by execution.costs, not guessed here.
            fee_usd=Decimal("0"),
            source=PROVIDER,
        )
        return JupiterQuote(
            quote=quote,
            raw=payload,
            price_impact_pct=_price_impact_pct(payload),
        )


def _price_impact_pct(payload: dict[str, Any]) -> Decimal:
    """Parse `priceImpactPct`, defaulting to zero when absent.

    Absent is treated as zero rather than as an error: it is an optional
    field, and a missing one must not take down a quote the risk engine
    could still evaluate through `worst_case_price`. Parsed via `str` so a
    float in the payload does not import binary rounding error.
    """
    raw = payload.get("priceImpactPct")
    if raw is None:
        return Decimal("0")
    try:
        impact = Decimal(str(raw))
    except InvalidOperation:
        raise ProviderError(
            PROVIDER, f"priceImpactPct was not a number: {raw!r}"
        ) from None
    # Jupiter reports a fraction (0.0012 = 0.12%); express it as a percent
    # so it is directly comparable to the config's *_pct fields.
    return impact * Decimal(100)


def _required_int(payload: dict[str, Any], key: str) -> int:
    if key not in payload:
        raise ProviderError(PROVIDER, f"quote response missing {key!r}")
    raw = payload[key]
    # int() would accept True as 1 and silently truncate 1.9 to 1. Atomic
    # amounts are exact quantities; a truncated or coerced one makes the
    # quoted price, the slippage check and the fill all quietly wrong.
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ProviderError(PROVIDER, f"{key!r} was not an integer: {raw!r}")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ProviderError(PROVIDER, f"{key!r} was not an integer: {raw!r}") from exc
