"""PostHog telemetry, sharing the logger's redaction path.

The rule from the `posthog-observability` skill is that redaction travels
with the event: a payload is redacted once, then the *same* dict goes to
both the structured log and PostHog. There is deliberately no way to send
an event that was not redacted — `track()` takes raw properties and
redacts them itself rather than trusting callers to have done it.

Telemetry is disabled unless explicitly configured. An unconfigured bot
logs exactly as before and sends nothing, so a missing API key degrades to
local-only observability rather than to a crash mid-trading-day.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from core.logging import get_logger, redact

logger = get_logger("tradecc.telemetry")

DEFAULT_DISTINCT_ID = "tradecc-bot"

# Fields that stay local: written to structured logs, never sent off-box.
#
# The wallet address is not a secret in the way a private key is — it is
# public on-chain data. It is withheld anyway because shipping it to a
# third party links this bot's whole trading history to one identity in
# someone else's system. `tx_signature` is the correlation key for
# telemetry instead: equally public, but it identifies one transaction
# rather than the account behind all of them.
#
# Redaction (core.logging.redact) still runs first; this is a further
# narrowing applied only to the telemetry copy, never to the log copy.
TELEMETRY_WITHHELD_FIELD_HINTS = (
    "wallet_address",
    "wallet_pubkey",
    "owner_address",
    "pubkey",
    "public_key",
)


def _is_withheld_from_telemetry(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in TELEMETRY_WITHHELD_FIELD_HINTS)


def for_telemetry(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop locals-only fields from an already-redacted payload.

    Applied at every depth. A top-level-only filter let a nested payload such
    as `{"context": {"wallet_address": ...}}` through, because the key it
    inspected was `context` — sending to PostHog exactly the field this list
    exists to keep local.
    """
    return _narrow(payload)


def _narrow(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _narrow(v)
            for k, v in value.items()
            if not _is_withheld_from_telemetry(str(k))
        }
    if isinstance(value, (list, tuple)):
        return [_narrow(v) for v in value]
    return value


class EventSink(Protocol):
    """Minimal sink interface. `PostHogSink` is the real one; tests use a fake."""

    def capture(self, distinct_id: str, event: str, properties: dict[str, Any]) -> None: ...


class PostHogSink:
    """Lazily-constructed PostHog client.

    The SDK is imported on first use so the core test suite neither needs
    the dependency nor risks a network client being built at import time.
    """

    def __init__(self, api_key: str, host: str | None = None) -> None:
        self._api_key = api_key
        self._host = host
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from posthog import Posthog  # imported lazily on purpose

            self._client = Posthog(
                project_api_key=self._api_key,
                host=self._host or "https://us.i.posthog.com",
            )
        return self._client

    def capture(self, distinct_id: str, event: str, properties: dict[str, Any]) -> None:
        self._ensure_client().capture(
            distinct_id=distinct_id, event=event, properties=properties
        )


class Telemetry:
    def __init__(
        self, sink: EventSink | None = None, distinct_id: str = DEFAULT_DISTINCT_ID
    ) -> None:
        self._sink = sink
        self._distinct_id = distinct_id

    @property
    def enabled(self) -> bool:
        return self._sink is not None

    def track(self, event: str, level: int = 20, **properties: Any) -> dict[str, Any]:
        """Redact once, log it, then send the same payload minus locals-only fields.

        Both copies come from a single `redact()` call, so telemetry can
        never carry something the log would have masked. The telemetry copy
        is then narrowed further — see TELEMETRY_WITHHELD_FIELD_HINTS.

        A sink failure must never interrupt trading: PostHog being down is
        an observability problem, not a reason to stop managing a position.
        """
        payload = redact(properties)
        logger.log(level, event, extra=payload)

        if self._sink is not None:
            try:
                self._sink.capture(self._distinct_id, event, for_telemetry(payload))
            except Exception as exc:  # noqa: BLE001 - telemetry must not raise
                logger.warning(
                    "telemetry_capture_failed",
                    extra={"event_name": event, "error": str(exc)},
                )
        return payload


_telemetry = Telemetry()


def configure_telemetry(
    sink: EventSink | None = None,
    env: dict[str, str] | None = None,
    distinct_id: str = DEFAULT_DISTINCT_ID,
) -> Telemetry:
    """Install the process-wide telemetry instance.

    With no explicit sink, PostHog is enabled only if POSTHOG_API_KEY is
    set. Absent that, telemetry stays a no-op.
    """
    global _telemetry
    if sink is None:
        environ = os.environ if env is None else env
        api_key = environ.get("POSTHOG_API_KEY")
        if api_key:
            sink = PostHogSink(api_key, environ.get("POSTHOG_HOST"))
    _telemetry = Telemetry(sink, distinct_id)
    return _telemetry


def get_telemetry() -> Telemetry:
    return _telemetry


def log_and_track(event: str, level: int = 20, **properties: Any) -> dict[str, Any]:
    """Log a structured event and mirror it to PostHog if configured."""
    return _telemetry.track(event, level=level, **properties)
