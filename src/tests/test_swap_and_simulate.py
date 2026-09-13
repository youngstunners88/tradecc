"""Stage 6a's two providers: build an unsigned swap, and simulate it.

Neither may transmit. The tests below assert that as a property, not as a
comment — a client that grows a send method fails here.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

from core.config import ProvidersConfig
from core.types import digest_of
from execution.helius import HeliusRpcClient
from execution.http import ProviderError, RetryPolicy
from execution.jupiter import JupiterSwapClient
from tests.test_http import FakeTransport, response


class RecordingTransport(FakeTransport):
    """FakeTransport that also keeps request bodies.

    Local rather than added to FakeTransport itself: test_helius.py already
    defines its own `Capturing` subclass with a `bodies` attribute holding
    parsed JSON, and a base-class attribute of the same name would double-fill
    it.
    """

    def __init__(self, *responses) -> None:
        super().__init__(*responses)
        self.sent: list[bytes | None] = []

    def request(self, method, url, *, headers=None, body=None, timeout=None):
        self.sent.append(body)
        return super().request(method, url, headers=headers, body=body, timeout=timeout)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
TX_BYTES = b"unsigned-swap-transaction"
TX_B64 = base64.b64encode(TX_BYTES).decode()
QUOTE_RESPONSE = {"inAmount": "10000000", "outAmount": "98241477", "routePlan": []}
PUBKEY = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"


def swap_client(transport) -> JupiterSwapClient:
    return JupiterSwapClient(
        ProvidersConfig(), transport=transport, retry=RetryPolicy(max_attempts=1)
    )


def rpc_client(transport) -> HeliusRpcClient:
    return HeliusRpcClient(
        ProvidersConfig(), api_key="k" * 20, transport=transport,
        retry=RetryPolicy(max_attempts=1),
    )


def sim_response(err=None, logs=None):
    return response(200, {"result": {"value": {"err": err, "logs": logs or []}}})


# --- Building an unsigned swap.


def test_build_swap_returns_bytes_that_hash_to_what_authorization_will_check():
    client = swap_client(FakeTransport(response(200, {
        "swapTransaction": TX_B64, "lastValidBlockHeight": 446_000_000,
    })))

    swap = client.build_swap(quote_response=QUOTE_RESPONSE, user_public_key=PUBKEY)

    assert swap.to_bytes() == TX_BYTES
    assert digest_of(swap.to_bytes()) == digest_of(TX_BYTES)
    assert swap.last_valid_block_height == 446_000_000


def test_the_quote_response_is_passed_through_unmodified():
    """Editing or rebuilding it invites a route that was never priced, and the
    transaction would not match the quote risk approved."""
    transport = RecordingTransport(response(200, {"swapTransaction": TX_B64}))

    swap_client(transport).build_swap(quote_response=QUOTE_RESPONSE, user_public_key=PUBKEY)

    sent = json.loads(transport.sent[-1])
    assert sent["quoteResponse"] == QUOTE_RESPONSE


def test_fees_are_sent_explicitly_when_given():
    """The cost model prices these exact numbers; a provider default would make
    the live trade a different trade than the backtest priced."""
    transport = RecordingTransport(response(200, {"swapTransaction": TX_B64}))

    swap_client(transport).build_swap(
        quote_response=QUOTE_RESPONSE,
        user_public_key=PUBKEY,
        compute_unit_limit=200_000,
        priority_fee_microlamports_per_cu=200_000,
    )

    sent = json.loads(transport.sent[-1])
    assert sent["computeUnitLimit"] == 200_000
    assert sent["computeUnitPriceMicroLamports"] == 200_000


def test_a_missing_swap_transaction_is_a_provider_error():
    client = swap_client(FakeTransport(response(200, {"lastValidBlockHeight": 1})))

    with pytest.raises(ProviderError):
        client.build_swap(quote_response=QUOTE_RESPONSE, user_public_key=PUBKEY)


def test_a_non_base64_swap_transaction_is_a_provider_error():
    """Garbage that reaches to_bytes() later is worse than garbage refused now."""
    client = swap_client(FakeTransport(response(200, {"swapTransaction": "not!base64!"})))

    with pytest.raises(ProviderError):
        client.build_swap(quote_response=QUOTE_RESPONSE, user_public_key=PUBKEY)


def test_building_requires_a_public_key():
    with pytest.raises(ValueError):
        swap_client(FakeTransport(response(200, {}))).build_swap(
            quote_response=QUOTE_RESPONSE, user_public_key=""
        )


def test_the_swap_client_cannot_sign_or_send():
    surface = {name for name in dir(JupiterSwapClient) if not name.startswith("_")}

    assert "build_swap" in surface
    for name in surface:
        assert not any(w in name.lower() for w in ("sign", "send", "submit", "keypair")), name


# --- Simulating it.


def test_a_clean_simulation_succeeds_and_is_digest_bound():
    outcome = rpc_client(FakeTransport(sim_response())).simulate_transaction(TX_B64, now=NOW)

    assert outcome.succeeded
    assert outcome.transaction_digest == digest_of(TX_BYTES)
    assert outcome.simulated_at == NOW


def test_a_simulation_error_is_a_failure_not_an_exception():
    """Preflight decides what to do with a failure; the client reports it."""
    outcome = rpc_client(
        FakeTransport(sim_response(err={"InstructionError": [0, "InsufficientFunds"]}))
    ).simulate_transaction(TX_B64, now=NOW)

    assert not outcome.succeeded
    assert "InsufficientFunds" in (outcome.error or "")


def test_an_unrecognised_error_shape_is_still_a_failure():
    """Guessing that an unknown error means success would send a failing tx."""
    outcome = rpc_client(FakeTransport(sim_response(err="something-new"))).simulate_transaction(
        TX_B64, now=NOW
    )

    assert not outcome.succeeded


def test_simulation_never_sets_sig_verify():
    """The transaction is unsigned at this stage; we are asking whether the
    swap would succeed, not whether a signature we do not have is valid."""
    transport = RecordingTransport(sim_response())

    rpc_client(transport).simulate_transaction(TX_B64, now=NOW)

    sent = json.loads(transport.sent[-1])
    assert sent["method"] == "simulateTransaction"
    assert sent["params"][1]["sigVerify"] is False


def test_a_malformed_simulation_response_raises():
    """An unanswered question is not a passing answer."""
    with pytest.raises(ProviderError):
        rpc_client(FakeTransport(response(200, {"result": "nope"}))).simulate_transaction(
            TX_B64, now=NOW
        )


def test_simulate_then_authorize_accepts_only_the_simulated_bytes():
    """The two halves, joined: simulating one transaction does not authorise
    sending another."""
    from decimal import Decimal

    from core.types import Mode, RiskDecision
    from live.preflight import authorize_send
    from tests.test_live_preflight import make_intent

    outcome = rpc_client(FakeTransport(sim_response())).simulate_transaction(TX_B64, now=NOW)

    good = authorize_send(
        intent=make_intent(), risk_decision=RiskDecision.approve(), simulation=outcome,
        transaction_bytes=TX_BYTES, configured_mode=Mode.LIVE, now=NOW,
    )
    assert good.authorized

    tampered = authorize_send(
        intent=make_intent(), risk_decision=RiskDecision.approve(), simulation=outcome,
        transaction_bytes=TX_BYTES + b"\x00", configured_mode=Mode.LIVE, now=NOW,
    )
    assert not tampered.authorized
    assert "different transaction" in tampered.describe()
