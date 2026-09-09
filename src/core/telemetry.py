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
        """Redact once, then log and send the identical payload.

        A sink failure must never interrupt trading: PostHog being down is
        an observability problem, not a reason to stop managing a position.
        """
        payload = redact(properties)
        logger.log(level, event, extra=payload)

        if self._sink is not None:
            try:
                self._sink.capture(self._distinct_id, event, payload)
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
