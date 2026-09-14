"""Helius RPC client — offline, with particular attention to key leakage."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from core.config import ProvidersConfig
from core.rate_limit import RateLimiter
from execution.helius import HeliusRpcClient
from execution.http import ProviderError, RetryPolicy
from tests.test_http import FakeTransport, response

FAKE_API_KEY = "helius-test-key-9f2a4c8e1b"
PUBKEY = "7xKqABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnop"


def make_client(transport) -> HeliusRpcClient:
    return HeliusRpcClient(
        providers=ProvidersConfig(),
        api_key=FAKE_API_KEY,
        transport=transport,
        limiter=RateLimiter(1000, 60.0, name="helius"),
        retry=RetryPolicy(max_attempts=1),
    )


def rpc(result) -> object:
    return response(200, {"jsonrpc": "2.0", "id": 1, "result": result})


def test_get_health():
    assert make_client(FakeTransport(rpc("ok"))).get_health() == "ok"


def test_get_balance_lamports():
    client = make_client(FakeTransport(rpc({"context": {"slot": 1}, "value": 1500000000})))

    assert client.get_balance_lamports(PUBKEY) == 1_500_000_000


def test_get_balance_sol_converts_exactly():
    client = make_client(FakeTransport(rpc({"context": {"slot": 1}, "value": 1500000000})))

    assert client.get_balance_sol(PUBKEY) == Decimal("1.5")


def test_get_latest_blockhash():
    client = make_client(FakeTransport(rpc({"context": {}, "value": {"blockhash": "abc123"}})))

    assert client.get_latest_blockhash() == "abc123"


def test_sends_valid_jsonrpc():
    transport = FakeTransport(rpc("ok"))
    make_client(transport).get_health()

    method, url = transport.requests[0]
    assert method == "POST"
    assert url.startswith("https://mainnet.helius-rpc.com/?api-key=")


def test_request_ids_increment():
    class Capturing(FakeTransport):
        def __init__(self, *r):
            super().__init__(*r)
            self.bodies = []

        def request(self, method, url, *, headers=None, body=None, timeout=None):
            self.bodies.append(json.loads(body))
            return super().request(method, url, headers=headers, body=body, timeout=timeout)

    transport = Capturing(rpc("ok"), rpc("ok"))
    client = make_client(transport)
    client.get_health()
    client.get_health()

    assert [b["id"] for b in transport.bodies] == [1, 2]


def test_rpc_error_raises_provider_error():
    payload = response(200, {"jsonrpc": "2.0", "id": 1, "error": {"message": "node behind"}})

    with pytest.raises(ProviderError, match="node behind"):
        make_client(FakeTransport(payload)).get_health()


def test_missing_result_raises():
    with pytest.raises(ProviderError, match="no result"):
        make_client(FakeTransport(response(200, {"jsonrpc": "2.0", "id": 1}))).get_health()


def test_malformed_balance_raises():
    with pytest.raises(ProviderError, match="no value"):
        make_client(FakeTransport(rpc({"context": {}}))).get_balance_lamports(PUBKEY)


def test_malformed_blockhash_raises():
    with pytest.raises(ProviderError, match="no blockhash"):
        make_client(FakeTransport(rpc({"value": {}}))).get_latest_blockhash()


def test_empty_api_key_is_refused():
    with pytest.raises(ValueError, match="API key"):
        HeliusRpcClient(ProvidersConfig(), api_key="", transport=FakeTransport())


def test_api_key_never_appears_in_logs(caplog):
    """The key rides in the query string, so a logged URL would leak it."""
    transport = FakeTransport(response(500), response(500))
    client = HeliusRpcClient(
        providers=ProvidersConfig(),
        api_key=FAKE_API_KEY,
        transport=transport,
        limiter=RateLimiter(1000, 60.0, name="helius"),
        retry=RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
    )

    with caplog.at_level("WARNING", logger="tradecc.http"):
        with pytest.raises(ProviderError):
            client.get_health()

    logged_url = caplog.records[0].url
    assert FAKE_API_KEY not in logged_url
    assert logged_url.endswith("***REDACTED***")
    assert FAKE_API_KEY not in caplog.text
    # The real key was still used on the wire.
    assert FAKE_API_KEY in transport.requests[0][1]


def test_error_message_does_not_leak_the_key():
    transport = FakeTransport(response(500), response(500))
    client = HeliusRpcClient(
        providers=ProvidersConfig(),
        api_key=FAKE_API_KEY,
        transport=transport,
        limiter=RateLimiter(1000, 60.0, name="helius"),
        retry=RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
    )

    with pytest.raises(ProviderError) as exc:
        client.get_health()

    assert FAKE_API_KEY not in str(exc.value)


def test_client_exposes_no_send_or_sign_method():
    """The client may read and may simulate. It may not send or sign.

    Simulation was added in Stage 6a and transmits nothing: `simulateTransaction`
    asks the cluster what *would* happen and is the enforcement point for
    CLAUDE.md rule 3. Sending and signing are still absent, and this pins that —
    the surface is asserted exactly, so a new method cannot appear unnoticed.
    """
    surface = {name for name in dir(HeliusRpcClient) if not name.startswith("_")}

    assert surface == {
        "get_health",
        "get_balance_lamports",
        "get_balance_sol",
        "get_latest_blockhash",
        "simulate_transaction",
    }


def test_no_method_anywhere_in_the_client_can_transmit():
    """Named-based guard, in case the surface assertion is ever relaxed."""
    forbidden = ("send", "sign", "submit", "broadcast", "transfer", "keypair", "secret")
    names = [name for name in dir(HeliusRpcClient) if not name.startswith("_")]

    for name in names:
        assert not any(word in name.lower() for word in forbidden), name
