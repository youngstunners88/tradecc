"""Jupiter quote client — quotes only, no transaction building.

Stage 2 reads prices and nothing else. There is no method here that
builds, signs, or sends a swap: live execution is Stage 6, behind the
validation gate.

Targets the free public host by default. Moving to the keyed host is a
config change, never a silent fallback when the free tier throttles — a
fallback that quietly starts spending money is the wrong shape for this.
"""

from __future__ import annotations

import base64
import binascii
import json
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
    """Jupiter quotes, normalised to one price convention.

    **Every Quote this client returns prices the traded token in the quote
    asset — "how much USDC is one SOL worth" — on both sides**, scaled out of
    atomic units so the number is directly comparable to a candle close.
    `worst_case_price` is always the adverse direction for that side: higher
    than expected for a BUY, lower for a SELL.

    That convention is load-bearing rather than cosmetic. `entry_price` comes
    from a BUY quote and `exit_price` from a SELL quote, and P&L is
    `(exit - entry) / entry`; the same numbers are compared against candle
    closes to fire stop-loss and take-profit. Two legs in different units
    produce arithmetic that is not wrong by a little.
    """

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
        input_decimals: int,
        output_decimals: int,
        *,
        side: Side = Side.BUY,
    ) -> Quote:
        return self.get_quote_detailed(
            input_mint, output_mint, amount_atomic, slippage_bps, amount_usd,
            input_decimals, output_decimals, side=side,
        ).quote

    def get_quote_detailed(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        slippage_bps: int,
        amount_usd: Decimal,
        input_decimals: int,
        output_decimals: int,
        *,
        side: Side = Side.BUY,
    ) -> JupiterQuote:
        if amount_atomic <= 0:
            raise ValueError("amount_atomic must be positive")
        if slippage_bps < 0:
            raise ValueError("slippage_bps must not be negative")
        # Required, not defaulted. Decimals are what turn an atomic ratio into
        # a price comparable to a candle close, and a default here would be a
        # silent wrong answer on every pair that does not happen to match it.
        if input_decimals < 0 or output_decimals < 0:
            raise ValueError("token decimals must not be negative")

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
        return self._to_quote(
            payload, input_mint, output_mint, amount_usd, side,
            input_decimals, output_decimals,
        )

    def _to_quote(
        self,
        payload: Any,
        input_mint: str,
        output_mint: str,
        amount_usd: Decimal,
        side: Side,
        input_decimals: int,
        output_decimals: int,
    ) -> JupiterQuote:
        if not isinstance(payload, dict):
            raise ProviderError(PROVIDER, "quote response was not a JSON object")

        in_amount = _required_int(payload, "inAmount")
        out_amount = _required_int(payload, "outAmount")
        # The minimum the route guarantees at the requested slippage. This is
        # the number the risk engine's slippage cap actually reads.
        threshold = _required_int(payload, "otherAmountThreshold")

        if in_amount <= 0:
            raise ProviderError(PROVIDER, "quote returned a non-positive input amount")
        if out_amount <= 0 or threshold <= 0:
            raise ProviderError(PROVIDER, "quote returned a non-positive output amount")

        # THE PRICE INVARIANT (see the class docstring): every Quote prices
        # **quote asset per token**, on both sides, scaled out of atomic units
        # so it is directly comparable to a candle close. `worst_case_price` is
        # always the adverse direction for that side — higher for a BUY, lower
        # for a SELL.
        #
        # This used to be `in/out` unconditionally, which is quote-per-token
        # only on a BUY. A SELL sends the token, so `in/out` was token per
        # quote asset — the reciprocal. Recording that as `exit_price` against
        # a BUY-derived `entry_price` reported **+$990 on a $10 position in a
        # flat market**, and the same prices were compared against candle
        # closes to fire stop-loss and take-profit. No test caught it because
        # the mock quote source returned one orientation for both sides.
        token_decimals = output_decimals if side is Side.BUY else input_decimals
        quote_decimals = input_decimals if side is Side.BUY else output_decimals
        scale = Decimal(10) ** (token_decimals - quote_decimals)

        if side is Side.BUY:
            expected_atomic = Decimal(in_amount) / Decimal(out_amount)
            worst_atomic = Decimal(in_amount) / Decimal(threshold)
        else:
            expected_atomic = Decimal(out_amount) / Decimal(in_amount)
            worst_atomic = Decimal(threshold) / Decimal(in_amount)

        expected_price = expected_atomic * scale
        worst_case_price = worst_atomic * scale

        # The token being traded, not whatever happens to be on the output
        # leg: on a SELL the output is the quote asset.
        token_mint = output_mint if side is Side.BUY else input_mint

        quote = Quote(
            token_mint=token_mint,
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


@dataclass(frozen=True)
class SwapTransaction:
    """An unsigned swap transaction from Jupiter, plus what it was built on.

    `transaction_base64` is what the chain will see once signed. Everything
    else is context for auditing: which blockhash it is bound to, and when it
    expires. Both matter because a transaction whose blockhash has aged out is
    not "slow", it is invalid, and re-signing a fresh one produces different
    bytes that must be simulated again.
    """

    transaction_base64: str
    last_valid_block_height: int | None
    raw: dict[str, Any]

    def to_bytes(self) -> bytes:
        """The serialised transaction. This is what authorisation binds to."""
        import base64

        return base64.b64decode(self.transaction_base64)


class JupiterSwapClient(JupiterQuoteClient):
    """Builds unsigned swap transactions. Cannot sign and cannot send.

    Separate from `JupiterQuoteClient` so that the read-only path stays
    read-only: code that only needs prices takes the quote client and has no
    method that could ever produce something sendable. Stage 6 takes this one.

    A transaction from here is inert. It has no signature, so submitting it
    would be rejected by the cluster — the capability to sign lives nowhere in
    this repo yet, and the send path requires a `SendAuthorization` bound to
    these exact bytes (`live.preflight`).
    """

    def build_swap(
        self,
        *,
        quote_response: dict[str, Any],
        user_public_key: str,
        wrap_and_unwrap_sol: bool = True,
        compute_unit_limit: int | None = None,
        priority_fee_microlamports_per_cu: int | None = None,
    ) -> SwapTransaction:
        """POST /swap/v1/swap — returns an UNSIGNED transaction.

        `quote_response` must be the raw quote payload Jupiter returned, passed
        through unmodified. Reconstructing or editing it invites a route that
        was never priced, and the resulting transaction would not match the
        quote risk approved.
        """
        if not user_public_key:
            raise ValueError("user_public_key is required to build a swap")

        body: dict[str, Any] = {
            "quoteResponse": quote_response,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": wrap_and_unwrap_sol,
        }
        # Fees are set explicitly, never left to a provider default: the cost
        # model prices these exact numbers, and a transaction that pays a
        # different fee than the backtest assumed is a different trade.
        if compute_unit_limit is not None:
            body["computeUnitLimit"] = compute_unit_limit
        if priority_fee_microlamports_per_cu is not None:
            body["computeUnitPriceMicroLamports"] = priority_fee_microlamports_per_cu

        payload = self._http.request(
            "POST",
            f"{self._base_url}/swap/v1/swap",
            headers={"Content-Type": "application/json"},
            body=json.dumps(body).encode(),
        ).json()

        encoded = payload.get("swapTransaction")
        if not isinstance(encoded, str) or not encoded:
            raise ProviderError(PROVIDER, f"swap response had no swapTransaction: {payload!r}")
        try:
            base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ProviderError(PROVIDER, "swapTransaction was not valid base64") from exc

        height = payload.get("lastValidBlockHeight")
        return SwapTransaction(
            transaction_base64=encoded,
            last_valid_block_height=height if isinstance(height, int) else None,
            raw=payload,
        )
