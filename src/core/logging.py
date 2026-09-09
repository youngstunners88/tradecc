"""Structured JSON logging with secret redaction.

Every signal, trade, and risk trigger is logged as one JSON object per
line so a trading day can be reconstructed and audited afterwards.

The redaction filter is a safety net, not a licence to be careless: the
first rule is still that keys never reach a log call. But logging is where
secrets leak in practice — an exception repr, a config dump, a debug line
someone added at 2am — so the sink scrubs known-sensitive field names and
any registered secret value before it writes.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

REDACTED = "***REDACTED***"

# Substring match, case-insensitive, against structured-field keys.
SENSITIVE_FIELD_HINTS = (
    "private_key",
    "privatekey",
    "secret",
    "seed",
    "mnemonic",
    "passphrase",
    "password",
    "api_key",
    "apikey",
    "token_auth",
    "authorization",
    "keypair",
)

_registered_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Register a literal secret value to scrub from all log output.

    Call this immediately after loading a key or API token. Short values are
    ignored — scrubbing a 3-character string would redact half the log.
    """
    if value and len(value) >= 8:
        _registered_secrets.add(value)


def _scrub_text(text: str) -> str:
    for secret in _registered_secrets:
        text = text.replace(secret, REDACTED)
    return text


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in SENSITIVE_FIELD_HINTS)


def _sanitize(value: Any, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: _sanitize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _scrub_text(str(value))


_STANDARD_RECORD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with extras flattened in and scrubbed."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": _scrub_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS:
                payload[key] = _sanitize(value, key=key)
        if record.exc_info:
            payload["exception"] = _scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO, stream: Any = None) -> None:
    """Install the JSON formatter as the root handler. Idempotent."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
