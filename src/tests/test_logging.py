"""Logging must never emit a key, even when something tries to log one."""

from __future__ import annotations

import io
import json
import logging
from decimal import Decimal

import pytest

from core.logging import REDACTED, configure_logging, get_logger, register_secret

FAKE_KEY = "4NfMxKQ8bU1sTESTKEYnotarealsecret9xZq2"


@pytest.fixture
def log_stream():
    stream = io.StringIO()
    configure_logging(level=logging.INFO, stream=stream)
    yield stream
    logging.getLogger().handlers.clear()


def emitted(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_emits_one_json_object_per_line(log_stream):
    get_logger("t").info("trade_executed", extra={"token_mint": "So111", "size_usd": Decimal("10")})

    records = emitted(log_stream)
    assert len(records) == 1
    assert records[0]["event"] == "trade_executed"
    assert records[0]["size_usd"] == "10"


def test_decimals_survive_as_exact_strings(log_stream):
    get_logger("t").info("pnl", extra={"pnl_usd": Decimal("-0.10")})

    assert emitted(log_stream)[0]["pnl_usd"] == "-0.10"


@pytest.mark.parametrize(
    "field",
    ["private_key", "wallet_private_key", "seed_phrase", "api_key", "PASSWORD", "keypair"],
)
def test_sensitive_field_names_are_redacted(log_stream, field):
    get_logger("t").info("config_loaded", extra={field: FAKE_KEY})

    assert emitted(log_stream)[0][field] == REDACTED


def test_nested_sensitive_fields_are_redacted(log_stream):
    get_logger("t").info("cfg", extra={"wallet": {"private_key": FAKE_KEY, "pubkey": "ok"}})

    record = emitted(log_stream)[0]
    assert record["wallet"]["private_key"] == REDACTED
    assert record["wallet"]["pubkey"] == "ok"


def test_registered_secret_is_scrubbed_from_an_innocuous_field(log_stream):
    register_secret(FAKE_KEY)

    get_logger("t").info("oops", extra={"debug_note": f"loaded {FAKE_KEY} ok"})

    assert FAKE_KEY not in log_stream.getvalue()
    assert REDACTED in emitted(log_stream)[0]["debug_note"]


def test_registered_secret_is_scrubbed_from_the_message_itself(log_stream):
    register_secret(FAKE_KEY)

    get_logger("t").info("failed to parse %s", FAKE_KEY)

    assert FAKE_KEY not in log_stream.getvalue()


def test_registered_secret_is_scrubbed_from_a_traceback(log_stream):
    register_secret(FAKE_KEY)

    try:
        raise ValueError(f"bad key: {FAKE_KEY}")
    except ValueError:
        get_logger("t").exception("decode_failed")

    assert FAKE_KEY not in log_stream.getvalue()


def test_trivially_short_values_are_not_registered(log_stream):
    register_secret("abc")

    get_logger("t").info("harmless abc text")

    assert "abc" in log_stream.getvalue()
